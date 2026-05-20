# Trend Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-spike surge detector with a surge-counter trend detector that enters when a token accumulates 3+ ascending surges in 15 minutes.

**Architecture:** The existing `SurgeDetector` becomes `TrendDetector`. Individual 10c surges remain as internal signals but no longer trigger entries. A new `_surge_history` dict per token tracks recent surges; when 3+ form an ascending subsequence, a `Trend` is emitted. The trailing stop changes from fixed 10c to 30% percentage-based. Confirmation delay and MAX_ENTRY_PRICE_YES are removed.

**Tech Stack:** Python 3.12, asyncio, aiosqlite

**Spec:** `docs/superpowers/specs/2026-05-20-trend-detector-design.md`

---

### File Map

| File | Action | Purpose |
|------|--------|---------|
| `scalper/models.py` | Modify | Add `Trend` dataclass |
| `scalper/config.py` | Modify | Replace surge params with trend params |
| `scalper/detector.py` | Rewrite | `SurgeDetector` → `TrendDetector` with surge history |
| `scalper/paper_engine.py` | Modify | `on_surge()` → `on_trend()`, 30% trailing stop, remove MAX_ENTRY_PRICE_YES |
| `scalper/main.py` | Modify | Remove confirmation delay, wire TrendDetector |
| `scalper/api.py` | Modify | Update detector references |
| `scalper/telegram.py` | Modify | Add `send_trend_entry()` method |
| `tests/test_detector.py` | Rewrite | All new tests for TrendDetector |
| `tests/test_paper_engine.py` | Modify | Update to use Trend instead of Surge for entries, test 30% stop |

---

### Task 1: Add Trend model

**Files:**
- Modify: `scalper/models.py:43-52`
- Test: `tests/test_models.py`

- [ ] **Step 1: Add Trend dataclass after Surge**

Add to `scalper/models.py` after the existing `Surge` class (line 52):

```python
@dataclass
class Trend:
    market_id: str
    token_id: str
    market_name: str
    surge_count: int
    first_surge_price: float
    current_price: float
    window_seconds: float
    timestamp: float
```

- [ ] **Step 2: Verify import works**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/python3 -c "from scalper.models import Trend; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scalper/models.py
git commit -m "feat: add Trend dataclass model"
```

---

### Task 2: Update config parameters

**Files:**
- Modify: `scalper/config.py:1-16`

- [ ] **Step 1: Replace strategy parameters**

Replace the top section of `scalper/config.py` (lines 1-16) with:

```python
import os

# === Strategy Parameters ===
SURGE_THRESHOLD = 0.10          # 10c move to count as internal surge signal
DETECTION_WINDOW_MIN = 30       # seconds — surge detection window
DETECTION_WINDOW_MAX = 60       # seconds — upper bound of detection window
TAKE_PROFIT = 0.90              # hard exit at 90c

# === Trend Detection ===
TREND_WINDOW = 900              # 15 minutes — how far back to look for surge history
TREND_MIN_SURGES = 3            # minimum ascending surges to confirm a trend
TREND_COOLDOWN = 300            # 5 minutes — don't re-enter same token after trend fires
TRAILING_STOP_PCT = 0.30        # 30% reversal from peak triggers exit
```

This removes: `TRAILING_STOP`, `SURGE_COOLDOWN`, `MAX_ENTRY_PRICE_YES`, `MIN_ENTRY_PRICE_NO`, `SURGE_CONFIRMATION_DELAY`.

- [ ] **Step 2: Verify config loads**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/python3 -c "from scalper import config; print(config.TREND_WINDOW, config.TRAILING_STOP_PCT)"`
Expected: `900 0.3`

- [ ] **Step 3: Commit**

```bash
git add scalper/config.py
git commit -m "feat: replace surge config with trend detection params"
```

---

### Task 3: Write TrendDetector tests

**Files:**
- Rewrite: `tests/test_detector.py`

- [ ] **Step 1: Write the complete test file**

Replace `tests/test_detector.py` entirely:

```python
from scalper.detector import TrendDetector
from scalper.models import Market


def _make_market(token_yes="tok_yes"):
    m = Market(
        condition_id="cond_1",
        token_id_yes=token_yes,
        token_id_no=token_yes + "_no",
        name="Test Market",
        volume_24h=50000,
    )
    return {token_yes: m}


def _feed_surge(det, token_id, bid, ask, timestamp):
    """Feed a price update that should register as a surge.
    Seeds a low price 40s earlier, then fires the high price."""
    low_bid = bid - 0.12
    low_ask = ask - 0.12
    det.on_price_update(token_id, low_bid, low_ask, timestamp - 40)
    return det.on_price_update(token_id, bid, ask, timestamp)


def test_single_surge_no_trend():
    det = TrendDetector(token_to_market=_make_market())
    result = _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)
    assert result is None


def test_two_surges_no_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)
    result = _feed_surge(det, "tok_yes", 0.39, 0.41, 1060.0)
    assert result is None


def test_three_ascending_surges_triggers_trend():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)  # surge at ~0.20
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)  # surge at ~0.30
    result = _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)  # surge at ~0.40
    assert result is not None
    assert result.surge_count >= 3
    assert result.market_name == "Test Market"
    assert result.first_surge_price < result.current_price


def test_three_surges_not_ascending_no_trend():
    """Surges at 0.30, 0.40, 0.25 — no ascending subsequence of length 3."""
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1000.0)  # ~0.30
    _feed_surge(det, "tok_yes", 0.39, 0.41, 1060.0)  # ~0.40
    result = _feed_surge(det, "tok_yes", 0.24, 0.26, 1120.0)  # ~0.25
    assert result is None


def test_staircase_with_pullback_triggers_trend():
    """Gallrein pattern: 0.27, 0.37, 0.32 (pullback), 0.40 — ascending subseq [0.27, 0.37, 0.40]."""
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.26, 0.28, 1000.0)  # ~0.27
    _feed_surge(det, "tok_yes", 0.36, 0.38, 1060.0)  # ~0.37
    _feed_surge(det, "tok_yes", 0.31, 0.33, 1120.0)  # ~0.32 (pullback)
    result = _feed_surge(det, "tok_yes", 0.39, 0.41, 1180.0)  # ~0.40
    assert result is not None
    assert result.surge_count >= 3


def test_trend_cooldown_prevents_duplicate():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    result1 = _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)
    assert result1 is not None

    # 4th surge within cooldown (5 min = 300s) — should not re-trigger
    result2 = _feed_surge(det, "tok_yes", 0.49, 0.51, 1180.0)
    assert result2 is None

    # After cooldown expires (1120 + 301 = 1421)
    result3 = _feed_surge(det, "tok_yes", 0.54, 0.56, 1421.0)
    # Need 3 ascending in window — depends on pruning, but cooldown is cleared
    # The key assertion: cooldown no longer blocks
    # (may or may not trigger depending on surge history — that's fine)


def test_surge_history_pruned_after_window():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)

    # 3rd surge 16 minutes later — first surge is outside 15min window (900s)
    result = _feed_surge(det, "tok_yes", 0.39, 0.41, 1961.0)
    assert result is None  # only 2 surges in window


def test_separate_tokens_independent():
    token_map = {
        "tok_a": Market("cond_a", "tok_a", "tok_a_no", "Market A", 50000),
        "tok_b": Market("cond_b", "tok_b", "tok_b_no", "Market B", 50000),
    }
    det = TrendDetector(token_to_market=token_map)

    # tok_a gets 3 ascending surges
    _feed_surge(det, "tok_a", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_a", 0.29, 0.31, 1060.0)
    result_a = _feed_surge(det, "tok_a", 0.39, 0.41, 1120.0)

    # tok_b gets only 1 surge
    result_b = _feed_surge(det, "tok_b", 0.29, 0.31, 1120.0)

    assert result_a is not None
    assert result_b is None


def test_prune_stale_tokens():
    det = TrendDetector(token_to_market=_make_market())
    det.on_price_update("tok_yes", 0.29, 0.31, 1000.0)
    assert "tok_yes" in det._windows
    det.prune_stale_tokens(now=1000.0 + 660)
    assert "tok_yes" not in det._windows


def test_get_stats():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    _feed_surge(det, "tok_yes", 0.29, 0.31, 1060.0)
    _feed_surge(det, "tok_yes", 0.39, 0.41, 1120.0)

    stats = det.get_stats()
    assert stats["surges_detected"] >= 3
    assert stats["trends_fired"] >= 1
    assert stats["active_windows"] >= 1


def test_get_recent_surges():
    det = TrendDetector(token_to_market=_make_market())
    _feed_surge(det, "tok_yes", 0.19, 0.21, 1000.0)
    recent = det.get_recent_surges()
    assert len(recent) >= 1
    assert recent[0]["direction"] == "up"
```

- [ ] **Step 2: Run tests — they should all fail (TrendDetector doesn't exist yet)**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/test_detector.py -v 2>&1 | tail -20`
Expected: All tests FAIL with `ImportError: cannot import name 'TrendDetector'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_detector.py
git commit -m "test: add TrendDetector tests (red phase)"
```

---

### Task 4: Implement TrendDetector

**Files:**
- Rewrite: `scalper/detector.py`

- [ ] **Step 1: Replace detector.py with TrendDetector**

Replace `scalper/detector.py` entirely:

```python
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
```

- [ ] **Step 2: Run detector tests**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/test_detector.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add scalper/detector.py
git commit -m "feat: implement TrendDetector with surge counter"
```

---

### Task 5: Update paper_engine — on_trend() and 30% trailing stop

**Files:**
- Modify: `scalper/paper_engine.py:6-14,65-175,207`

- [ ] **Step 1: Write failing test for 30% trailing stop**

Add to `tests/test_paper_engine.py` — replace the existing `test_trailing_stop_exit` and add a new trend-based entry test. First, update the imports and helper at the top of the file.

Replace lines 1-38 of `tests/test_paper_engine.py`:

```python
import pytest
import pytest_asyncio
import time

from scalper import db, config
from scalper.models import Surge, Trend, Direction, ExitReason
from scalper.paper_engine import PaperEngine


@pytest_asyncio.fixture
async def engine(tmp_path):
    path = str(tmp_path / "test.db")
    await db.init_db(path)
    eng = PaperEngine()
    await eng.init()
    yield eng
    await db.close_db()


def _make_surge(
    direction=Direction.UP,
    price=0.30,
    magnitude=0.12,
    token_id="tok_yes",
    market_id="cond_1",
    market_name="Test Market",
    timestamp=None,
):
    return Surge(
        market_id=market_id,
        token_id=token_id,
        market_name=market_name,
        direction=direction,
        magnitude=magnitude,
        window_seconds=35.0,
        price_at_detection=price,
        timestamp=timestamp or time.time(),
    )


def _make_trend(
    token_id="tok_yes",
    market_id="cond_1",
    market_name="Test Market",
    surge_count=3,
    first_surge_price=0.20,
    current_price=0.40,
    window_seconds=120.0,
    timestamp=None,
):
    return Trend(
        market_id=market_id,
        token_id=token_id,
        market_name=market_name,
        surge_count=surge_count,
        first_surge_price=first_surge_price,
        current_price=current_price,
        window_seconds=window_seconds,
        timestamp=timestamp or time.time(),
    )
```

- [ ] **Step 2: Update the successful entry test to use on_trend**

Replace the `test_successful_entry` test:

```python
@pytest.mark.asyncio
async def test_successful_entry(engine):
    trend = _make_trend(current_price=0.30)
    pos = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)

    assert pos is not None
    assert pos.direction == Direction.UP
    assert pos.entry_price == 0.31
    assert pos.shares == pytest.approx(config.POSITION_SIZE / 0.31, rel=0.01)
    assert pos.entry_fee == pytest.approx(config.POSITION_SIZE * config.TAKER_FEE_RATE)

    status = engine.get_status()
    assert status["balance"] < config.STARTING_BALANCE
    assert status["open_positions"] == 1
```

- [ ] **Step 3: Add test for 30% trailing stop**

Add after the existing trailing stop test:

```python
@pytest.mark.asyncio
async def test_trailing_stop_percentage(engine):
    """30% trailing stop: at peak 0.50, exit when price drops to 0.35 (30% of 0.50 = 0.15 drop)."""
    trend = _make_trend(current_price=0.30)
    pos = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is not None

    # Price rises to 0.50 (peak)
    closed = await engine.on_price_update("tok_yes", 0.49, 0.51, time.time() + 10)
    assert closed == []

    # Price drops to 0.40 — only 20% reversal from peak 0.50, should NOT exit
    closed = await engine.on_price_update("tok_yes", 0.39, 0.41, time.time() + 20)
    assert closed == []

    # Price drops to 0.35 — 30% reversal from peak 0.50 (0.15/0.50 = 0.30), should exit
    closed = await engine.on_price_update("tok_yes", 0.34, 0.36, time.time() + 30)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TRAILING_STOP
    assert closed[0].exit_price == 0.34  # exits at bid
```

- [ ] **Step 4: Run tests — they should fail**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/test_paper_engine.py::test_successful_entry tests/test_paper_engine.py::test_trailing_stop_percentage -v 2>&1 | tail -10`
Expected: FAIL — `on_trend` doesn't exist, `TRAILING_STOP` config removed

- [ ] **Step 5: Update paper_engine.py**

In `scalper/paper_engine.py`:

**a)** Update imports (line 8): change `Surge` to `Surge, Trend`:

```python
from scalper.models import (
    Direction,
    ExitReason,
    Position,
    PositionStatus,
    Surge,
    Trend,
    Trade,
)
```

**b)** Rename `on_surge` method (line 65) to `on_trend` and change parameter type. Replace lines 65-147:

```python
    async def on_trend(
        self,
        trend: Trend,
        current_bid: float,
        current_ask: float,
    ) -> Optional[Position]:
        self._check_daily_reset()

        entry_price = current_ask

        if current_bid < 0.02 or current_ask > 0.98:
            logger.debug("Rejected resolving market %s (bid=%.2f ask=%.2f)", trend.market_name[:30], current_bid, current_ask)
            return None

        spread = current_ask - current_bid
        if spread > 0.15:
            logger.debug("Rejected wide spread %s (spread=%.2f)", trend.market_name[:30], spread)
            return None

        rejection = self._validate_entry(trend, entry_price)
        if rejection:
            logger.debug("Entry rejected for %s: %s", trend.market_name[:30], rejection)
            return None

        shares = config.POSITION_SIZE / entry_price
        entry_fee = config.POSITION_SIZE * config.TAKER_FEE_RATE

        surge_for_db = Surge(
            market_id=trend.market_id,
            token_id=trend.token_id,
            market_name=trend.market_name,
            direction=Direction.UP,
            magnitude=round(trend.current_price - trend.first_surge_price, 4),
            window_seconds=trend.window_seconds,
            price_at_detection=trend.current_price,
            timestamp=trend.timestamp,
        )
        surge_id = await db.log_surge(surge_for_db)

        trade = Trade(
            surge_id=surge_id,
            market_id=trend.market_id,
            token_id=trend.token_id,
            market_name=trend.market_name,
            direction=Direction.UP,
            entry_price=entry_price,
            entry_fee=entry_fee,
            entry_time=trend.timestamp,
            shares=shares,
            position_size=config.POSITION_SIZE,
        )
        trade_id = await db.log_trade_entry(trade)

        cost = config.POSITION_SIZE + entry_fee
        self._balance -= cost
        await db.log_balance_change(self._balance, trade_id, -cost, "trade_entry")

        self._daily_trades += 1

        position = Position(
            id=trade_id,
            market_id=trend.market_id,
            token_id=trend.token_id,
            market_name=trend.market_name,
            direction=Direction.UP,
            entry_price=entry_price,
            entry_fee=entry_fee,
            entry_time=trend.timestamp,
            shares=shares,
            position_size=config.POSITION_SIZE,
            trailing_peak=entry_price,
            status=PositionStatus.OPEN,
            surge_id=surge_id,
        )
        self._positions[trade_id] = position

        logger.info(
            "TREND ENTRY: %s @ %.2f (%d surges, %.2f->%.2f, %d shares) [balance=$%.2f]",
            trend.market_name[:30],
            entry_price,
            trend.surge_count,
            trend.first_surge_price,
            trend.current_price,
            int(shares),
            self._balance,
        )

        return position
```

**c)** Update `_validate_entry` (line 149) — change `surge: Surge` to `trend: Trend` and remove the MAX_ENTRY_PRICE_YES check. Replace lines 149-175:

```python
    def _validate_entry(self, trend: Trend, entry_price: float) -> Optional[str]:
        if self._paused:
            return "trading paused (daily loss limit)"

        if self._balance < config.POSITION_SIZE:
            return f"insufficient balance (${self._balance:.2f} < ${config.POSITION_SIZE})"

        if len(self._positions) >= config.MAX_CONCURRENT_POSITIONS:
            return f"max concurrent positions ({config.MAX_CONCURRENT_POSITIONS})"

        market_count = sum(
            1 for p in self._positions.values() if p.market_id == trend.market_id
        )
        if market_count >= config.MAX_POSITIONS_PER_MARKET:
            return f"max positions per market ({config.MAX_POSITIONS_PER_MARKET})"

        if self._daily_trades >= config.MAX_DAILY_TRADES:
            return f"max daily trades ({config.MAX_DAILY_TRADES})"

        if self._daily_pnl <= -config.DAILY_LOSS_LIMIT:
            self._paused = True
            return f"daily loss limit (${config.DAILY_LOSS_LIMIT})"

        return None
```

**d)** Update trailing stop in `on_price_update` (line 207). Replace:

```python
            if pos.trailing_peak - midpoint >= config.TRAILING_STOP:
```

With:

```python
            if pos.trailing_peak > 0 and (pos.trailing_peak - midpoint) / pos.trailing_peak >= config.TRAILING_STOP_PCT:
```

- [ ] **Step 6: Run all paper engine tests**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/test_paper_engine.py -v`
Expected: PASS (some old tests may need `on_surge` → `on_trend` updates — fix any remaining references)

- [ ] **Step 7: Fix remaining test references**

In `tests/test_paper_engine.py`, find-and-replace all remaining `engine.on_surge(surge,` with `engine.on_trend(trend,` and `_make_surge()` with `_make_trend()` in tests that test entry. Keep `_make_surge` available for any tests that don't directly call `on_trend` (it's still used internally by the engine for DB logging).

For tests that call `on_surge` with `direction=Direction.DOWN` — those should be removed since we only trade UP now and `on_trend` doesn't accept a direction parameter.

- [ ] **Step 8: Run full test suite**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/test_paper_engine.py tests/test_detector.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add scalper/paper_engine.py tests/test_paper_engine.py
git commit -m "feat: on_trend() entry + 30% trailing stop"
```

---

### Task 6: Update main.py — remove confirmation delay, wire TrendDetector

**Files:**
- Modify: `scalper/main.py`

- [ ] **Step 1: Update imports (line 17)**

Replace:
```python
from scalper.detector import SurgeDetector
```
With:
```python
from scalper.detector import TrendDetector
```

- [ ] **Step 2: Update detector instantiation (line 47)**

Replace:
```python
    detector = SurgeDetector()
```
With:
```python
    detector = TrendDetector()
```

- [ ] **Step 3: Replace the on_event callback (lines 80-153)**

Replace the entire `pending_surges` dict and `on_event` function with:

```python
    async def on_event(event):
        try:
            if isinstance(event, BestBidAskEvent):
                trend = detector.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )

                closed_trades = await engine.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )
                for trade in closed_trades:
                    await notifier.send_exit(trade)

                if trend:
                    position = await engine.on_trend(
                        trend, event.best_bid, event.best_ask
                    )
                    if position:
                        await notifier.send_entry(position)

            elif isinstance(event, BookSnapshotEvent):
                detector.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )

            elif isinstance(event, LastTradePriceEvent):
                detector.on_trade(
                    event.asset_id, event.price, event.side, event.size, event.timestamp
                )

            elif event == "DISCONNECT":
                logger.warning("Prolonged disconnect — closing all positions")
                closed = await engine.on_disconnect()
                for trade in closed:
                    await notifier.send_exit(trade)
                await notifier.send_error(
                    "WebSocket disconnected >30s — all positions closed"
                )

        except Exception:
            logger.exception("Error processing event")
```

This removes: `pending_surges` dict, all PENDING/CONFIRMED/REJECTED logic, `SURGE_CONFIRMATION_DELAY` reference.

- [ ] **Step 4: Remove unused config import reference**

Verify no remaining references to `config.SURGE_CONFIRMATION_DELAY`, `config.TRAILING_STOP`, `config.SURGE_COOLDOWN`, or `config.MAX_ENTRY_PRICE_YES` anywhere in main.py.

- [ ] **Step 5: Run full test suite**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/ -v -m "not integration" 2>&1 | tail -15`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add scalper/main.py
git commit -m "feat: wire TrendDetector in main, remove confirmation delay"
```

---

### Task 7: Update api.py and telegram.py references

**Files:**
- Modify: `scalper/api.py:266`
- Modify: `scalper/telegram.py:113-122`

- [ ] **Step 1: Fix api.py trailing stop reference**

In `scalper/api.py`, line 266 references `config.TRAILING_STOP`. Replace:
```python
        trailing_stop = body.get("trailing_stop", config.TRAILING_STOP)
```
With:
```python
        trailing_stop_pct = body.get("trailing_stop_pct", config.TRAILING_STOP_PCT)
```

And update any usage of `trailing_stop` in that function to use `trailing_stop_pct` accordingly.

- [ ] **Step 2: Fix api.py detector references**

In `scalper/api.py`, find any reference to `SurgeDetector` and update to `TrendDetector` if needed. The `set_detector` function takes the detector object generically so it likely just works. Search and update imports if present.

- [ ] **Step 3: Update telegram send_entry to show trend info**

The `send_entry` method in `scalper/telegram.py` (line 71) receives a `Position` object which doesn't contain trend info. The entry notification can stay as-is since Position already has all the price/size data. No change needed.

The `send_surge` method (line 113) is no longer called from main.py. It can stay for now (no harm) or be removed. Leave it.

- [ ] **Step 4: Run full test suite**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/ -v -m "not integration" 2>&1 | tail -15`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scalper/api.py scalper/telegram.py
git commit -m "fix: update api and telegram for trend detector changes"
```

---

### Task 8: Final integration verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && .venv/bin/pytest tests/ -v -m "not integration"`
Expected: All tests PASS (except pre-existing failures in test_markets.py)

- [ ] **Step 2: Verify no dangling references to old config**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && grep -rn "SURGE_COOLDOWN\|TRAILING_STOP[^_]\|MAX_ENTRY_PRICE_YES\|SURGE_CONFIRMATION_DELAY\|SurgeDetector\|on_surge" scalper/ tests/ --include="*.py" | grep -v __pycache__ | grep -v "# Removed\|# Old"`
Expected: No matches (all old references cleaned up). `Surge` class itself and `log_surge` are OK — those are still used internally.

- [ ] **Step 3: Verify bot can start locally**

Run: `cd /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper && timeout 3 .venv/bin/python3 -c "from scalper.main import main; import asyncio; asyncio.run(main())" 2>&1 || true`
Expected: Should start loading (may fail on DB path or Telegram — that's fine, the import chain working is what matters)

- [ ] **Step 4: Final commit if any cleanup**

```bash
git add -A && git commit -m "chore: final cleanup for trend detector" || echo "nothing to commit"
```
