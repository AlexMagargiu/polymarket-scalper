import logging
import time
from typing import Optional

from scalper import config, db

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 5
FLUSH_INTERVAL = 30


class PriceTracker:
    def __init__(self):
        self._tracked: set[str] = set()  # token_ids currently being tracked
        self._last_snapshot: dict[str, float] = {}  # token_id -> last snapshot timestamp
        self._pending: list[tuple] = []  # buffered snapshots to flush
        self._last_flush: float = 0.0

    async def init(self):
        """Load unresolved tracked tokens from DB on startup."""
        rows = await db.get_unresolved_tracked_tokens()
        for row in rows:
            self._tracked.add(row["token_id"])
        if self._tracked:
            logger.info("Tracker loaded %d unresolved tokens", len(self._tracked))

    async def track(self, token_id: str, market_id: str, market_name: str, reason: str, timestamp: float):
        """Start tracking a token. Called when surge/trend detected or trade entered."""
        if token_id in self._tracked:
            return
        self._tracked.add(token_id)
        await db.add_tracked_token(
            token_id, market_id, market_name, reason,
            db._ts_to_iso(timestamp),
        )

    async def on_price_update(self, token_id: str, bid: float, ask: float, timestamp: float):
        """Record price snapshot if tracked and interval elapsed. Detect resolution."""
        if token_id not in self._tracked:
            return

        midpoint = (bid + ask) / 2

        # Check if market resolved (require narrow spread to avoid false positives on illiquid markets)
        spread = ask - bid
        if (bid < config.RESOLVING_BID or ask > config.RESOLVING_ASK) and spread < 0.10:
            await self._flush()
            self._last_flush = timestamp
            resolution_price = midpoint
            await db.resolve_tracked_token(token_id, resolution_price, db._ts_to_iso(timestamp))
            self._tracked.discard(token_id)
            self._last_snapshot.pop(token_id, None)
            logger.info(
                "RESOLVED: token %s...%s at %.2f",
                token_id[:8], token_id[-4:], resolution_price,
            )
            return

        # Snapshot at interval
        last = self._last_snapshot.get(token_id, 0)
        if timestamp - last >= SNAPSHOT_INTERVAL:
            self._last_snapshot[token_id] = timestamp
            self._pending.append((
                token_id,
                db._ts_to_iso(timestamp),
                round(midpoint, 6),
                round(bid, 6),
                round(ask, 6),
            ))

        # Periodic flush
        if timestamp - self._last_flush >= FLUSH_INTERVAL:
            await self._flush()
            self._last_flush = timestamp

    async def _flush(self):
        if not self._pending:
            return
        batch = list(self._pending)
        try:
            await db.log_price_snapshots_batch(batch)
            self._pending.clear()
        except Exception:
            logger.warning("Failed to flush %d price snapshots, will retry", len(batch))

    async def flush(self):
        """Public flush for shutdown."""
        await self._flush()

    async def cleanup_removed_tokens(self, active_token_ids: set[str]):
        removed = self._tracked - active_token_ids
        for token_id in removed:
            await db.resolve_tracked_token(token_id, -1.0, db._ts_to_iso(time.time()))
            self._tracked.discard(token_id)
            self._last_snapshot.pop(token_id, None)
        if removed:
            logger.info("Cleaned up %d tracked tokens removed from market feed", len(removed))

    def get_stats(self) -> dict:
        return {
            "tracked_tokens": len(self._tracked),
            "pending_snapshots": len(self._pending),
        }
