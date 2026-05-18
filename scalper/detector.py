import logging
import time
from collections import deque
from typing import Optional

from scalper import config
from scalper.models import Direction, Market, PricePoint, Surge

logger = logging.getLogger(__name__)


class SurgeDetector:
    def __init__(self, token_to_market: dict[str, Market] | None = None):
        self._windows: dict[str, deque[PricePoint]] = {}
        self._cooldowns: dict[tuple[str, str], float] = {}
        self._token_to_market: dict[str, Market] = token_to_market or {}
        self._surges_up: int = 0
        self._surges_down: int = 0
        self._recent_surges: deque[dict] = deque(maxlen=50)

    def set_token_map(self, token_to_market: dict[str, Market]):
        self._token_to_market = token_to_market

    def on_price_update(
        self,
        token_id: str,
        best_bid: float,
        best_ask: float,
        timestamp: float,
    ) -> Optional[Surge]:
        midpoint = (best_bid + best_ask) / 2
        point = PricePoint(
            timestamp=timestamp,
            midpoint=midpoint,
            best_bid=best_bid,
            best_ask=best_ask,
        )

        if token_id not in self._windows:
            self._windows[token_id] = deque()
        window = self._windows[token_id]
        window.append(point)

        cutoff = timestamp - config.PRICE_WINDOW_MAX_AGE
        while window and window[0].timestamp < cutoff:
            window.popleft()

        window_start = timestamp - config.DETECTION_WINDOW_MAX  # 60s ago
        window_end = timestamp - config.DETECTION_WINDOW_MIN  # 30s ago

        relevant_points = [
            p for p in window if window_start <= p.timestamp <= window_end
        ]

        if not relevant_points:
            return None

        min_point = min(relevant_points, key=lambda p: p.midpoint)

        if midpoint - min_point.midpoint >= config.SURGE_THRESHOLD:
            return self._try_fire_surge(
                token_id=token_id,
                direction=Direction.UP,
                magnitude=midpoint - min_point.midpoint,
                window_seconds=timestamp - min_point.timestamp,
                price_at_detection=midpoint,
                timestamp=timestamp,
            )

        return None

    def _try_fire_surge(
        self,
        token_id: str,
        direction: Direction,
        magnitude: float,
        window_seconds: float,
        price_at_detection: float,
        timestamp: float,
    ) -> Optional[Surge]:
        cooldown_key = (token_id, direction.value)
        last_fired = self._cooldowns.get(cooldown_key, 0)

        if timestamp - last_fired < config.SURGE_COOLDOWN:
            return None

        self._cooldowns[cooldown_key] = timestamp

        market = self._token_to_market.get(token_id)
        market_id = market.condition_id if market else ""
        market_name = market.name if market else "Unknown"

        surge = Surge(
            market_id=market_id,
            token_id=token_id,
            market_name=market_name,
            direction=direction,
            magnitude=round(magnitude, 4),
            window_seconds=round(window_seconds, 1),
            price_at_detection=round(price_at_detection, 4),
            timestamp=timestamp,
        )

        if direction == Direction.UP:
            self._surges_up += 1
        else:
            self._surges_down += 1

        self._recent_surges.appendleft(self._surge_to_dict(surge))

        logger.info(
            "SURGE %s: %s — %+.0fc in %.0fs (price: %.2f)",
            direction.value.upper(),
            market_name[:40],
            magnitude * 100,
            window_seconds,
            price_at_detection,
        )

        return surge

    def on_trade(
        self, token_id: str, price: float, side: str, size: float, timestamp: float
    ):
        pass

    def prune_stale_tokens(self, now: float | None = None):
        if now is None:
            now = time.time()
        stale_cutoff = now - 600
        stale_tokens = [
            tid
            for tid, window in self._windows.items()
            if not window or window[-1].timestamp < stale_cutoff
        ]
        for tid in stale_tokens:
            del self._windows[tid]

        expired = [key for key, ts in self._cooldowns.items() if ts < stale_cutoff]
        for key in expired:
            del self._cooldowns[key]

        if stale_tokens:
            logger.debug("Pruned %d stale token windows", len(stale_tokens))

    def get_stats(self) -> dict:
        now = time.time()
        active_cooldowns = sum(
            1 for ts in self._cooldowns.values() if now - ts < config.SURGE_COOLDOWN
        )
        return {
            "surges_up": self._surges_up,
            "surges_down": self._surges_down,
            "active_windows": len(self._windows),
            "cooldowns_active": active_cooldowns,
        }

    def get_recent_surges(self) -> list[dict]:
        return list(self._recent_surges)

    @staticmethod
    def _surge_to_dict(surge: Surge) -> dict:
        from datetime import datetime, timezone

        return {
            "id": 0,
            "timestamp": datetime.fromtimestamp(
                surge.timestamp, tz=timezone.utc
            ).isoformat(),
            "market_id": surge.market_id,
            "token_id": surge.token_id,
            "market_name": surge.market_name,
            "direction": surge.direction.value,
            "magnitude": surge.magnitude,
            "window_seconds": surge.window_seconds,
            "price_at_detection": surge.price_at_detection,
            "traded": False,
        }
