import logging
import time
from collections import deque
from typing import Optional

from scalper import config
from scalper.models import Direction, Market, PricePoint, Surge, Trend

logger = logging.getLogger(__name__)


class TrendDetector:
    def __init__(self, token_to_market: dict[str, Market] | None = None):
        self._windows: dict[str, deque[PricePoint]] = {}
        self._surge_cooldowns: dict[str, float] = {}
        self._surge_history: dict[str, list[tuple[float, float]]] = {}
        self._trend_cooldowns: dict[str, float] = {}
        self._token_to_market: dict[str, Market] = token_to_market or {}
        self._surges_detected: int = 0
        self._trends_fired: int = 0
        self._recent_surges: deque[dict] = deque(maxlen=50)

    def set_token_map(self, token_to_market: dict[str, Market]):
        self._token_to_market = token_to_market

    def on_price_update(
        self,
        token_id: str,
        best_bid: float,
        best_ask: float,
        timestamp: float,
    ) -> Optional[Trend]:
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

        surge = self._check_surge(token_id, midpoint, timestamp)
        if surge:
            self._record_surge(token_id, surge, timestamp)
            return self._check_trend(token_id, midpoint, timestamp)

        return None

    def _check_surge(self, token_id: str, midpoint: float, timestamp: float) -> Optional[Surge]:
        window = self._windows[token_id]
        window_start = timestamp - config.DETECTION_WINDOW_MAX
        window_end = timestamp - config.DETECTION_WINDOW_MIN

        relevant_points = [
            p for p in window if window_start <= p.timestamp <= window_end
        ]
        if not relevant_points:
            return None

        min_point = min(relevant_points, key=lambda p: p.midpoint)
        magnitude = midpoint - min_point.midpoint

        if magnitude < config.SURGE_THRESHOLD:
            return None

        last_surge = self._surge_cooldowns.get(token_id, 0)
        if timestamp - last_surge < 30:
            return None
        self._surge_cooldowns[token_id] = timestamp

        market = self._token_to_market.get(token_id)
        market_id = market.condition_id if market else ""
        market_name = market.name if market else "Unknown"

        surge = Surge(
            market_id=market_id,
            token_id=token_id,
            market_name=market_name,
            direction=Direction.UP,
            magnitude=round(magnitude, 4),
            window_seconds=round(timestamp - min_point.timestamp, 1),
            price_at_detection=round(midpoint, 4),
            timestamp=timestamp,
        )

        self._surges_detected += 1
        self._recent_surges.appendleft(self._surge_to_dict(surge))

        logger.info(
            "SURGE: %s — %+.0fc in %.0fs (price: %.2f)",
            market_name[:40],
            magnitude * 100,
            timestamp - min_point.timestamp,
            midpoint,
        )

        return surge

    def _record_surge(self, token_id: str, surge: Surge, timestamp: float):
        if token_id not in self._surge_history:
            self._surge_history[token_id] = []
        history = self._surge_history[token_id]

        cutoff = timestamp - config.TREND_WINDOW
        self._surge_history[token_id] = [
            (ts, price) for ts, price in history if ts > cutoff
        ]

        self._surge_history[token_id].append(
            (timestamp, surge.price_at_detection)
        )

    def _check_trend(self, token_id: str, midpoint: float, timestamp: float) -> Optional[Trend]:
        last_trend = self._trend_cooldowns.get(token_id, 0)
        if timestamp - last_trend < config.TREND_COOLDOWN:
            return None

        history = self._surge_history.get(token_id, [])
        asc_len, first_price = _longest_ascending_subsequence(history)

        if asc_len < config.TREND_MIN_SURGES:
            return None

        self._trend_cooldowns[token_id] = timestamp
        self._trends_fired += 1

        market = self._token_to_market.get(token_id)
        market_id = market.condition_id if market else ""
        market_name = market.name if market else "Unknown"

        first_ts = history[0][0]
        trend = Trend(
            market_id=market_id,
            token_id=token_id,
            market_name=market_name,
            surge_count=asc_len,
            first_surge_price=first_price,
            current_price=round(midpoint, 4),
            window_seconds=round(timestamp - first_ts, 1),
            timestamp=timestamp,
        )

        logger.info(
            "TREND: %s — %d ascending surges, %.2f->%.2f over %.0fs",
            market_name[:40],
            asc_len,
            first_price,
            midpoint,
            timestamp - first_ts,
        )

        return trend

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
            self._surge_history.pop(tid, None)
            self._surge_cooldowns.pop(tid, None)

        expired = [tid for tid, ts in self._trend_cooldowns.items() if ts < stale_cutoff]
        for tid in expired:
            del self._trend_cooldowns[tid]

        if stale_tokens:
            logger.debug("Pruned %d stale token windows", len(stale_tokens))

    def get_stats(self) -> dict:
        now = time.time()
        active_cooldowns = sum(
            1 for ts in self._trend_cooldowns.values() if now - ts < config.TREND_COOLDOWN
        )
        trending_tokens = sum(
            1 for history in self._surge_history.values()
            if _longest_ascending_subsequence(history)[0] >= config.TREND_MIN_SURGES
        )
        return {
            "surges_detected": self._surges_detected,
            "trends_fired": self._trends_fired,
            "active_windows": len(self._windows),
            "cooldowns_active": active_cooldowns,
            "trending_tokens": trending_tokens,
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


def _longest_ascending_subsequence(
    history: list[tuple[float, float]],
) -> tuple[int, float]:
    """Return (length, first_price) of the longest ascending subsequence by price.

    Finds non-consecutive ascending subsequences — pullbacks between
    surges are tolerated. E.g. [0.27, 0.37, 0.32, 0.40] -> [0.27, 0.37, 0.40] (length 3).

    Greedy approach: for each starting index, greedily extend the longest
    ascending chain. O(n^2) but n < 50 surges per token so irrelevant.
    """
    if not history:
        return 0, 0.0
    best_len = 0
    best_first = 0.0
    for i in range(len(history)):
        chain_len = 1
        last_price = history[i][1]
        for j in range(i + 1, len(history)):
            if history[j][1] > last_price:
                chain_len += 1
                last_price = history[j][1]
        if chain_len > best_len:
            best_len = chain_len
            best_first = history[i][1]
    return best_len, best_first
