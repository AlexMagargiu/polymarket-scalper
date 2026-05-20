# Trend Detector Design

Replace the single-spike surge detector with a trend-following system that tracks sustained momentum over time.

## Problem

The current detector fires on individual 10c surges (30-60s window) and enters immediately. Backtest data from 71 trades shows:
- 6.25% win rate, -$814 total P&L
- 50% of trades had zero MFE (price never moved in our favor)
- The bot buys the top of completed spikes that immediately revert
- Real momentum events like Gallrein KY-04 (19 surges, 0.17->0.65+ over 2 hours) were detected but never traded because each individual surge had a brief pullback that failed the 5-second confirmation

The signal we want: "this token keeps surging repeatedly" not "this token just spiked once."

## Design Decisions

- **Approach:** Surge counter. Count surges per token; when 3+ ascending surges accumulate in a time window, that's a confirmed trend. Simplest option, reuses existing surge infrastructure.
- **Replaces spike detector entirely.** Individual surges become internal signals, not entry triggers.
- **Exit:** 30% percentage-based trailing stop replaces fixed 10c stop. Scales with position value, tolerates normal pullbacks during staircase climbs.
- **Direction:** UP trends only (YES-side).

## Architecture

### New Model: `Trend`

```python
@dataclass
class Trend:
    market_id: str
    token_id: str
    market_name: str
    surge_count: int          # how many surges triggered this trend
    first_surge_price: float  # price at first surge in the sequence
    current_price: float      # price at trend detection
    window_seconds: float     # time span from first to last surge
    timestamp: float
```

### TrendDetector (replaces SurgeDetector)

Same file (`detector.py`), same interface to `main.py`.

**State per token:**
- `_windows: dict[str, deque[PricePoint]]` — existing rolling price window for surge detection
- `_surge_history: dict[str, list[tuple[float, float]]]` — new: `{token_id: [(timestamp, price_at_detection), ...]}` for surges in the last 15 minutes
- `_trend_cooldowns: dict[str, float]` — new: `{token_id: last_trend_timestamp}` cooldown per token after trend fires

**On each price update:**
1. Detect 10c surge as before (internal signal, not emitted to caller)
2. When surge fires, append `(timestamp, price_at_detection)` to that token's surge history
3. Prune surge history entries older than `TREND_WINDOW` (15 minutes)
4. Check trend condition (see below)
5. If trend fires, apply `TREND_COOLDOWN` (5 minutes) to prevent re-entry on same trend

**Trend condition — 3+ ascending surges:**
Scan the surge history for an ascending subsequence of length >= `TREND_MIN_SURGES` (3). An ascending subsequence means each surge's detection price is strictly higher than the previous selected surge's price. This does NOT require all surges to be ascending — pullbacks between surges are tolerated.

Example with Gallrein:
```
history: [(22:20, 0.27), (22:22, 0.37), (22:23, 0.32), (22:25, 0.40)]
ascending subsequence: [0.27, 0.37, 0.40] -> length 3 -> TREND
```

Algorithm: iterate through surge history, greedily build longest ascending subsequence. If length >= 3, trend fires.

**Return value:** `on_price_update()` returns `Optional[Trend]` instead of `Optional[Surge]`. The `Trend` object contains the surge count, first/current price, and time span.

### Config Changes

```python
# === Trend Detection ===
SURGE_THRESHOLD = 0.10          # 10c move to count as a surge (internal signal)
DETECTION_WINDOW_MIN = 30       # seconds — surge detection window (unchanged)
DETECTION_WINDOW_MAX = 60       # seconds (unchanged)
TREND_WINDOW = 900              # 15 minutes — how far back to look for surge history
TREND_MIN_SURGES = 3            # minimum ascending surges to confirm a trend
TREND_COOLDOWN = 300            # 5 minutes — don't re-enter same token after trend fires
TRAILING_STOP_PCT = 0.30        # 30% reversal from peak triggers exit

# === Removed ===
# SURGE_COOLDOWN (replaced by TREND_COOLDOWN)
# TRAILING_STOP (replaced by TRAILING_STOP_PCT)
# SURGE_CONFIRMATION_DELAY (no longer needed — trend IS the confirmation)
# MAX_ENTRY_PRICE_YES (removed — enter at any price if trend confirms)
# MIN_ENTRY_PRICE (already removed)
```

### Entry Flow (main.py)

```
price update arrives
  -> detector.on_price_update() returns Optional[Trend]
  -> engine.on_price_update() checks trailing stops on open positions
  -> if trend:
       engine.on_trend(trend, bid, ask) -> enters position or rejects
```

No confirmation delay. No pending surges dict. The 3-surge ascending pattern IS the confirmation.

**Removed from main.py:**
- `pending_surges` dict
- All PENDING/CONFIRMED/REJECTED logic
- Surge logging for untraded surges (trend detector handles this internally)

### paper_engine.py Changes

**`on_trend()` replaces `on_surge()`:**
- Same validation: position limits, balance, daily loss, resolving filter, spread filter
- Removed: `MAX_ENTRY_PRICE_YES` check
- Removed: `MIN_ENTRY_PRICE` check (already gone)
- Entry price: `current_ask` (unchanged)

**Trailing stop in `on_price_update()`:**
```python
# Old:
if pos.trailing_peak - midpoint >= config.TRAILING_STOP:

# New:
if pos.trailing_peak > 0 and (pos.trailing_peak - midpoint) / pos.trailing_peak >= config.TRAILING_STOP_PCT:
```

**Take profit stays at 0.90** (unchanged).

### Database

`surges` table stays for logging individual surges (useful for analysis). When a trend fires and triggers a trade, log the trend as a surge entry with `traded=1`. The `surge_id` foreign key on `trades` points to this entry. No new tables needed.

### Models

- Add `Trend` dataclass to `models.py`
- Keep `Surge` dataclass (used internally by detector, logged to DB)
- `Trade.surge_id` unchanged — points to the surge/trend log entry that triggered the trade

### Telegram Notifications

- Entry notification shows: "TREND ENTRY: {market} - {surge_count} surges, {first_price}->{current_price} over {window}s"
- Exit notification: unchanged (already shows entry/exit/pnl)

## What Stays the Same

- WebSocket multi-connection pool (recently fixed)
- Sports market filter
- Market refresh every 5 minutes
- Position sizing ($25), max concurrent (10), max per market (3)
- Daily loss limit ($500)
- Resolving market filter (bid < 2c, ask > 98c)
- Spread filter (> 15c)
- API server and dashboard endpoints
- Telegram notifications (content changes, not plumbing)

## Testing

- Unit tests for ascending subsequence detection (various patterns: clean staircase, pullbacks, flat, descending)
- Unit test: 3 surges in window triggers trend, 2 does not
- Unit test: cooldown prevents duplicate trends
- Unit test: stale surge history is pruned
- Unit test: 30% trailing stop math at various price levels
- Integration: Gallrein-like scenario replayed through detector

## Rollback

If trend detector underperforms, config params can be tuned:
- Lower `TREND_MIN_SURGES` to 2 (more entries, noisier)
- Widen `TREND_WINDOW` to 30 minutes (catches slower climbs)
- Tighten `TRAILING_STOP_PCT` to 0.20 (exit earlier)

The old spike detector code can be restored from git if needed.
