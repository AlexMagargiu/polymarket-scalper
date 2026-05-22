# End-of-Day Codebase Sweep

Run this sweep at the end of every supervisor session after all coding, trade analysis, and discussion is complete. It catches regressions, dead code, logging gaps, and logic bugs introduced during the session before they ship to production.

## How to Run

Launch 9 parallel Explore agents with the prompts below. Wait for all to complete, then present **consolidated, prioritized findings** to the user. Verify critical findings manually before reporting (grep for symbols, read the actual lines). Dismiss false positives.

**Do NOT create or modify any files during the sweep. Research only.**

---

## Findings Tracking System

Each agent has a corresponding JSON file in `sweep_results/` that tracks all findings across sessions. This provides:
- **No repeated false positives** -- agents skip previously dismissed findings
- **Regression detection** -- agents verify previous fixes are still in place
- **Quality trending** -- issues going down over time = codebase improving

### Finding Schema

```json
{
  "id": "agent-NNN",
  "file": "scalper/detector.py",
  "line": 57,
  "category": "unused_function",
  "description": "_check_surge -- zero callers outside class",
  "found_date": "2026-05-22",
  "found_session": "S1",
  "status": "fixed | false_positive | wont_fix | open | regression",
  "resolution_date": "2026-05-22",
  "resolution_notes": "Removed in session S2",
  "verify_grep": "_check_surge"
}
```

**Status values:**
- `open` -- found, not yet addressed
- `fixed` -- resolved in code, verify_grep confirms
- `false_positive` -- agent was wrong, not a real issue
- `wont_fix` -- real but intentional / not worth fixing
- `regression` -- was fixed, but verify_grep shows it's back

### Agent Preamble (prepend to every agent prompt)

Each agent prompt below must be prefixed with:

```
FINDINGS TRACKING: Before starting, read sweep_results/<agent_file>.json if it exists.

For each finding with status="fixed":
  Run verify_grep. If matches found -> report as REGRESSION with original ID.
  If no matches -> fix confirmed, skip silently.

For each finding with status="false_positive" or "wont_fix":
  Skip entirely. Do not re-report.

For each finding with status="open":
  Check current code state. If fixed since last session, note it.
  If still present, include in report with original ID.

For NEW findings not in the JSON, assign the next sequential ID
(e.g., if last ID was "dead-003", new one is "dead-004").

At the END of your report, output the complete updated JSON array
so the supervisor can write it to the findings file after review.
```

### Supervisor Workflow (after agents complete)

1. Review agent reports and verify findings as usual
2. For each finding, set the correct status (the agent proposes, you decide)
3. Write the updated JSON to `sweep_results/<agent>.json`
4. Agents DO NOT write files -- only the supervisor does

---

## Agent 1: Dead Code Sweep

**Findings file:** `sweep_results/dead_code.json`

```
Very thorough dead code sweep of the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/dead_code.json if it exists. Follow the tracking preamble above.

Find:
1. Unused functions -- grep for each function/method definition (def foo) then search for callers across all .py files (exclude the definition line and test files). A function is dead if it has ZERO callers anywhere in production code.
2. Unused imports -- imports at the top of each module that are never referenced in that file's body. Check every file in scalper/.
3. Unused classes/dataclasses -- classes defined in scalper/models.py (Direction, PositionStatus, ExitReason, Market, PricePoint, Surge, Trend, Position, Trade) or elsewhere that are never instantiated or referenced. Check enum members too -- e.g., Direction.DOWN is defined but is it ever used outside telegram.py format strings?
4. Orphan model fields -- dataclass fields that are set but never read, or read but never set. Check Position.max_adverse_excursion, Trade.max_favorable_excursion, Market.is_sports, Market.token_id_no carefully.
5. Unused config parameters -- constants in scalper/config.py that are never imported or referenced in any other file.

Focus on scalper/ package. Key files: config.py, models.py, detector.py, paper_engine.py, tracker.py, main.py, api.py, db.py, markets.py, telegram.py, backtest.py.

CRITICAL VERIFICATION REQUIREMENT -- DO NOT SKIP THIS:
For EVERY function you think is dead, you MUST run:
  grep -rn "function_name" scalper/ tests/ --include="*.py" | grep -v "def function_name"
and check ALL matches -- not just the definition line. A function is only dead if it has ZERO callers
anywhere in the codebase. Common false positive patterns in Python:
- Method defined in a class, called via self.method_name() or instance.method_name()
- Function imported in one file and called from another
- Function called via string reference (e.g., getattr, or in dict mappings)
- Functions used as callbacks (e.g., on_event passed to ws.listen)
- Functions called from tests/ that are still needed for testability

Specific areas to check thoroughly:
- detector.py: on_trade() method appears to be a no-op (pass). Is it called? Should it be?
- markets.py: compute_market_changes() -- is it called directly or only via refresh_markets()?
- db.py: mark_surge_traded() -- is it called? Or only through log_trade_entry()?
- websocket.py: WebSocketManager.connect() -- is it a no-op? WebSocketManager._parse_event() -- static method wrapping module-level function
- api.py: every handler function -- verify each is registered in create_api_app()
- models.py: ExitReason.DAILY_LOSS, ExitReason.MANUAL -- are these enum values ever used in code?
- backtest.py: export_surges() -- is it called from anywhere?
- tracker.py: get_stats() -- is it exposed via any API endpoint?

Report: file:line, symbol name, evidence ("0 callers via grep -- full grep output shown"). HIGH-CONFIDENCE findings only. Include updated JSON at end.
```

## Agent 2: Logging Gaps

**Findings file:** `sweep_results/logging_gaps.json`

```
Very thorough audit of logging gaps in the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/logging_gaps.json if it exists. Follow the tracking preamble above.

The bot uses Python logging (import logging, logger = logging.getLogger(__name__)) across all modules. Every decision branch that affects trading should produce a log event at INFO level minimum.

Find:
1. Silent rejection paths in paper_engine.py:
   - on_trend(): Check every early return path. Currently logs "REJECTED" for resolving market, entry price too high, wide spread, and _validate_entry() rejections. But does _validate_entry() log at all, or does it just return a string? Are all 6 validation checks inside _validate_entry() logged before returning?
   - on_price_update(): Does it log when a trailing stop triggers? When take profit triggers? When no exit condition is met?
   - close_stale_positions(): Does it log the number of stale positions found, or only individual closes?
   - on_disconnect(): Does it log the exit price used for each position?

2. Silent paths in detector.py:
   - on_price_update(): When a token has no market in _token_to_market, does it log?
   - _check_surge(): When surge cooldown blocks a surge, is that logged at DEBUG?
   - _check_trend(): When trend cooldown blocks a trend, is that logged? When ascending subsequence is < TREND_MIN_SURGES, is that logged?
   - prune_stale_tokens(): Currently logs at DEBUG -- should this be INFO when tokens are actually pruned?

3. Silent paths in tracker.py:
   - on_price_update(): When a token resolves, it logs. But when a snapshot is skipped (interval not elapsed), is there any DEBUG log?
   - _flush(): Does it log how many snapshots were flushed?

4. Silent paths in main.py:
   - on_event(): The BookSnapshotEvent handler calls detector.on_price_update() but ignores the returned surge and trend. These are assigned to _surge, _trend but never used. Is this intentional? If a surge/trend fires from a book snapshot, it's silently dropped.
   - market_refresher_task(): When refresh finds no changes, does it log?
   - Error handling: The catch-all `except Exception: logger.exception(...)` is good, but are there inner try/except blocks that swallow errors silently?

5. Silent paths in websocket.py:
   - _parse_event(): When parsing fails (returns None), no log is emitted. High-volume messages could silently fail.
   - _listen_loop(): When json.loads fails, it silently continues. When data is not a list and _parse_event returns None, it's silent.
   - add_tokens() / remove_tokens(): Some exception handlers just `pass` with no logging.

6. DEBUG logs that should be INFO:
   - Check all logger.debug() calls -- any that log production-relevant decisions (like "pruned N stale tokens") should be INFO.

Report: file:line, function name, the specific silent branch, what log event SHOULD be there. Include updated JSON at end.
```

## Agent 3: Missed Trade Gaps

**Findings file:** `sweep_results/missed_trade_gaps.json`

```
Very thorough audit of "Missed Trade" gaps in the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/missed_trade_gaps.json if it exists. Follow the tracking preamble above.

Trace the full pipeline: WebSocket event -> detector.on_price_update() -> surge -> trend -> engine.on_trend() -> db.log_trade_entry() -> tracker.track(). Find ALL paths where data is lost or not persisted.

1. Trends that fire but never reach DB:
   - In main.py on_event(): If detector returns a trend, engine.on_trend() is called. But what if engine.on_trend() raises an exception? The outer try/except catches it, but the trend is never logged to DB (db.log_trend). Trace the exact order: is db.log_trend() called AFTER engine.on_trend()? What if engine raises before we get there?
   - If engine.on_trend() returns (None, rejection_reason), the trend IS logged. But if it raises, the entire on_event handler falls to the except block and the trend is lost.

2. Surges that aren't tracked:
   - In main.py: surge_id is set from db.log_surge() only if surge is truthy. But what if db.log_surge() fails? surge_id would be None, and the subsequent tracker.track() call and trend entry would have no surge linkage.
   - BookSnapshotEvent handler: surge and trend from detector.on_price_update() are captured as _surge, _trend but never acted upon. If a real surge/trend fires from a book snapshot, it's completely lost -- not logged to DB, not sent to engine, not tracked.

3. Price history gaps:
   - tracker.on_price_update() only records snapshots for tokens in self._tracked. But tokens only get added to _tracked when surge/trend/trade fires. Price history before the first surge is lost entirely. Is this intentional?
   - If tracker._flush() fails (DB write error), self._pending is still cleared. Data is lost silently. Check: does _flush() clear _pending before or after the DB write?

4. Tracked tokens that never resolve:
   - tracker.py: Resolution detection uses RESOLUTION_BID (0.02) and RESOLUTION_ASK (0.98). But what if a market resolves exactly at 0.02 or 0.98? Check the comparison operators (< vs <=).
   - What if a token is removed from the market list (market_refresher removes it) but it's still in tracker._tracked? It will never get price updates again and never resolve.
   - Is there a cleanup mechanism for tracked tokens that have been unresolved for too long?

5. Trade exits that aren't persisted:
   - engine._close_position() writes to DB via db.log_trade_exit(). But what if the DB write fails? The position is still removed from self._positions (del self._positions[trade_id]) and balance is still adjusted. This creates an in-memory/DB inconsistency.
   - on_disconnect(): If _close_position() fails for one position, does the loop continue to close others?

6. Missing surge-to-trade linkage:
   - In main.py, surge_id is passed to engine.on_trend(). But surge_id comes from db.log_surge() which is only called when surge is truthy. If the trend fires without a simultaneous surge (trend checks surge_history, not just current surge), surge_id will be None. Is the trend-to-surge link always correctly established?

Report: the specific code path, what data is lost, impact (missed signals, broken audit trail, inconsistent DB state). Include updated JSON at end.
```

## Agent 4: Logic Audit

**Findings file:** `sweep_results/logic_audit.json`

```
Very thorough logic audit of the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/logic_audit.json if it exists. Follow the tracking preamble above.

Find:

1. TRAILING STOP MATH (paper_engine.py:213):
   - The trailing stop check: `(pos.trailing_peak - midpoint) / pos.trailing_peak >= config.TRAILING_STOP_PCT`
   - This is a PERCENTAGE drop from peak. But config.TRAILING_STOP_PCT = 0.10 means 10% reversal from peak, NOT 10 cents. A position with trailing_peak=0.50 would need to drop to 0.45 (5c) to trigger, while a position at trailing_peak=0.90 needs to drop to 0.81 (9c). Is this the intended behavior? The SPEC says "10c reversal from peak" but the code implements percentage-based trailing stop.
   - Division by zero: What if pos.trailing_peak is 0? The code checks `pos.trailing_peak > 0` but what sets it -- could it ever be 0.0 after initialization?

2. MFE/MAE CALCULATIONS (paper_engine.py:205-210):
   - MFE = midpoint - entry_price (favorable = price went up). This only works for UP direction. If Direction.DOWN were ever used, MFE/MAE would be inverted.
   - MAE = entry_price - midpoint (adverse = price went down). Same directional assumption.
   - Are these values ever negative? max_favorable_excursion starts at 0.0 and only updates if mfe > current, so it should always be >= 0 for UP trades.

3. FEE CALCULATIONS:
   - Entry fee (paper_engine.py:99): `config.POSITION_SIZE * config.TAKER_FEE_RATE` -- fee on notional.
   - Exit fee (paper_engine.py:238): `pos.shares * exit_price * config.TAKER_FEE_RATE` -- fee on exit proceeds.
   - Are these consistent? Entry fee is on POSITION_SIZE ($25), exit fee is on shares * exit_price. If price moved, exit proceeds != position_size. Is this intentional asymmetry?
   - Balance deduction on entry (line 117): `cost = config.POSITION_SIZE + entry_fee`. So total cost = $25 + $0.50 = $25.50.
   - Balance addition on exit (line 255): `proceeds = pos.shares * exit_price - exit_fee`. This is the raw proceeds minus fee.
   - PnL formula (line 239): `(exit_price - entry_price) * shares - entry_fee - exit_fee`. Verify this matches the balance changes.

4. ASCENDING SUBSEQUENCE ALGORITHM (detector.py:228-255):
   - The docstring says "longest ascending subsequence" but the algorithm is GREEDY, not dynamic programming. It finds the longest GREEDY ascending chain from each starting point. This is NOT the standard Longest Increasing Subsequence (LIS). For [0.20, 0.40, 0.25, 0.30], greedy from index 0 gives [0.20, 0.40] (length 2) because after 0.40, 0.25 < 0.40. But LIS would give [0.20, 0.25, 0.30] (length 3). Is the greedy behavior intentional?
   - The function returns (length, first_price, first_timestamp). With the greedy approach, does it always find the optimal starting point?

5. RESOLUTION DETECTION (tracker.py:48):
   - `if bid < RESOLUTION_BID or ask > RESOLUTION_ASK` -- this is `bid < 0.02 OR ask > 0.98`.
   - What about normal wide spreads? A market with bid=0.01, ask=0.50 would trigger resolution detection (bid < 0.02) even if it's just illiquid. Should this also check that the spread is narrow (indicating actual resolution, not just low liquidity)?

6. STALE POSITION TIMEOUT (paper_engine.py:301-319):
   - Uses `self._last_update_time.get(pos.token_id, pos.entry_time)`. If _last_update_time is never set for a token (no price update since init), it falls back to entry_time. But entry_time is a UNIX timestamp from when the trade was opened -- potentially days ago if the bot restarted and loaded from DB. Would stale positions be closed immediately on restart?

7. PURGE LOGIC (db.py:429-439):
   - Purge nullifies surge_id on trades before deleting surges: `UPDATE trades SET surge_id = NULL WHERE surge_id IN (SELECT ...)`. This preserves trade records but breaks the audit trail. Is that acceptable?
   - Trends are deleted without checking if they reference active trades.
   - balance_log is never purged. It will grow forever.

8. SPREAD CALCULATIONS (paper_engine.py:87-90):
   - `spread = current_ask - current_bid`. Rejected if > 0.15. But this is compared BEFORE the entry at current_ask. A 15c spread means you're already 15c underwater at entry. Is 0.15 the right threshold?

9. TAKE PROFIT vs TRAILING STOP PRIORITY (paper_engine.py:213-221):
   - Trailing stop is checked first (line 213), then take profit (line 217). But if BOTH trigger simultaneously, exit_reason will be overwritten to TAKE_PROFIT. Is this the intended priority? It means take profit always wins over trailing stop when midpoint >= 0.90 and trailing stop is also triggered.

Report: file:line, exact code, what's wrong, impact (wrong trades, wrong P&L, missed exits, incorrect stats). Include updated JSON at end.
```

## Agent 5: Config vs Code Drift

**Findings file:** `sweep_results/config_drift.json`

```
Very thorough audit of config-vs-code drift in the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/config_drift.json if it exists. Follow the tracking preamble above.

Check:

1. Config parameters defined but never referenced:
   - List every constant in scalper/config.py. For each, grep across all .py files (excluding config.py itself) to verify it's actually used.
   - Specifically check: DETECTION_WINDOW_MIN, DETECTION_WINDOW_MAX, SURGE_THRESHOLD, STALE_THRESHOLD, CLOB_API_URL, WS_MAX_TOKENS_PER_CONNECTION.

2. Hardcoded values that should be in config:
   - tracker.py: SNAPSHOT_INTERVAL = 5, FLUSH_INTERVAL = 30, RESOLUTION_BID = 0.02, RESOLUTION_ASK = 0.98 -- these are module-level constants, not in config.py. Should they be?
   - paper_engine.py:77: `current_bid < 0.02 or current_ask > 0.98` -- hardcoded resolving market thresholds that mirror tracker.py's RESOLUTION_BID/ASK but aren't imported from a shared location.
   - paper_engine.py:88: `spread > 0.15` -- hardcoded spread threshold not in config.
   - detector.py:75: `timestamp - last_surge < 30` -- hardcoded 30-second surge cooldown not in config.
   - detector.py:169: `stale_cutoff = now - 600` -- hardcoded 10-minute stale cutoff. config.STALE_THRESHOLD is 60 seconds but this uses 600. Which is correct?
   - main.py:179: `await asyncio.sleep(900)` -- status reporter interval hardcoded to 15 minutes.
   - main.py:211: `await asyncio.sleep(300)` -- stale pruner interval hardcoded to 5 minutes.
   - main.py:215: `await db.purge_old_data(retention_days=60)` -- retention_days hardcoded.
   - backtest.py simulate_params: References config.TAKER_FEE_RATE directly -- correct. But also hardcodes direction logic for "up" vs "down" strings rather than using Direction enum.

3. Config parameters used inconsistently:
   - config.STALE_THRESHOLD = 60 seconds. Who uses it? detector.py prune_stale_tokens() uses 600 (10 minutes) as the stale cutoff. paper_engine.py uses config.STALE_POSITION_TIMEOUT = 7200 (2 hours). Are these the same concept at different layers, or is STALE_THRESHOLD orphaned?
   - config.SURGE_THRESHOLD vs detector.py _check_surge(): Verify the comparison uses config.SURGE_THRESHOLD and not a hardcoded value.
   - config.TRAILING_STOP_PCT: Verify paper_engine.py uses this and backtest.py simulate_params uses the parameter correctly.

4. Config snapshot in DB:
   - db.log_trade_entry() saves config_trailing_pct, config_max_entry, config_trend_min_surges. But NOT config.SURGE_THRESHOLD, config.TAKER_FEE_RATE, or config.POSITION_SIZE. These are needed for backtest accuracy. Are they missing intentionally?

5. Dashboard config alignment:
   - Does the dashboard reference any config values (like STARTING_BALANCE, position limits)? Are they hardcoded in the dashboard or fetched from the API?

Report: both locations for each mismatch, what the discrepancy is, impact. Include updated JSON at end.
```

## Agent 6: Performance / Memory Audit

**Findings file:** `sweep_results/performance.json`

```
Very thorough performance and memory audit of the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/performance.json if it exists. Follow the tracking preamble above.

This bot runs 24/7 on a Hetzner VPS (8GB RAM) and processes hundreds of WebSocket messages per second. Find:

1. UNBOUNDED DICTS in detector.py:
   - self._windows: dict[str, deque[PricePoint]] -- pruned via PRICE_WINDOW_MAX_AGE (120s) per-token, but the dict itself grows with every new token. Tokens removed from market refresh are NOT removed from _windows until prune_stale_tokens() runs. How often does prune_stale_tokens run (every 300s in main.py)? Could thousands of dead token windows accumulate between prunes?
   - self._surge_cooldowns: dict[str, float] -- grows forever. Only pruned by prune_stale_tokens(). Verify entries are actually cleaned up.
   - self._surge_history: dict[str, list[tuple]] -- pruned to TREND_WINDOW (900s) in _record_surge(), but only when a new surge fires for that token. Tokens that stop surging keep their old history forever until prune_stale_tokens().
   - self._trend_cooldowns: dict[str, float] -- pruned in prune_stale_tokens() but only for entries older than 600s.

2. UNBOUNDED DICTS in paper_engine.py:
   - self._last_prices: dict[str, tuple] -- grows with every token that has an open position. But are entries removed when positions close? Check _close_position -- it deletes from self._positions but NOT from _last_prices or _last_update_time. These dicts grow forever.
   - self._last_update_time: dict[str, float] -- same issue.

3. UNBOUNDED DICTS in websocket.py:
   - _WebSocketConnection._events_by_type: dict[str, int] -- counter dict, bounded by event type count (3 types), fine.
   - WebSocketManager._token_to_conn: dict[str, conn] -- cleaned via remove_tokens(). Verify add_tokens/remove_tokens keep it consistent.

4. DB WRITE FREQUENCY:
   - tracker.py writes price_history snapshots every 5 seconds per tracked token, flushed every 30 seconds. With 100 tracked tokens, that's ~20 writes/sec (100 tokens * 1 snapshot/5s = 20 snapshots/s). Flushed as a batch every 30s = 600 rows per batch insert. Is SQLite WAL mode handling this well under load?
   - Every surge logs to DB immediately (db.log_surge). Every trend logs to DB immediately (db.log_trend). Every trade entry and exit logs immediately. With db.commit() after every write, that's potentially dozens of commits per second during active markets.
   - price_history table: With 100 tracked tokens snapshotting every 5s, that's 1.7M rows/day. The only cleanup is purge_old_data(retention_days=60), so potentially 100M+ rows. Is there a vacuum or compaction? Does the idx_price_history_token_ts index handle this?

5. ASYNCIO TASK LEAKS:
   - main.py creates tasks in a list and cancels them on shutdown. But what about tasks created by WebSocketManager.add_tokens() (line 352-355 in websocket.py)? These are appended to self._listener_tasks but are they cleaned up when close() is called?
   - The heartbeat task in _WebSocketConnection._listen_loop() is created and cancelled in a try/finally. Verify it doesn't leak on unexpected exceptions.
   - ws.listen() creates listener tasks for each connection. If a connection is added mid-run (via add_tokens creating a new connection), its task is appended to _listener_tasks. On close(), all tasks are cancelled. This looks correct, but verify.

6. MISSING CONNECTION CLEANUP:
   - aiohttp session in markets.py fetch_markets(): Uses `async with aiohttp.ClientSession()` which properly closes. Good.
   - WebSocket connections: _WebSocketConnection.close() closes the websocket. WebSocketManager.close() closes all connections. Verify all paths lead to proper cleanup.
   - aiosqlite connection: db.close_db() closes it. Verify all shutdown paths call this.

7. SQLite WAL UNDER LOAD:
   - PRAGMA journal_mode=WAL is set in init_db(). But no other pragmas (busy_timeout, synchronous, cache_size). Under heavy write load (20+ commits/sec), readers might see stale data or writers might get SQLITE_BUSY. Is busy_timeout set?

Report: file:line, what grows unbounded or leaks, estimated impact (MB/day or rows/day), fix suggestion. Include updated JSON at end.
```

## Agent 7: Dashboard / API Parity

**Findings file:** `sweep_results/dashboard_parity.json`

```
Very thorough audit of dashboard-to-API parity in the codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/dashboard_parity.json if it exists. Follow the tracking preamble above.

The dashboard is a Next.js app in dashboard/src/. The API server is in scalper/api.py. TypeScript types are in dashboard/src/lib/types.ts.

Check:

1. API endpoint coverage -- every route registered in api.py create_api_app() (lines 302-324):
   - /api/health, /api/balance, /api/trades, /api/trades/open, /api/surges, /api/stats
   - /api/markets, /api/markets/stats, /api/ws/status, /api/detector/stats, /api/surges/live
   - /api/positions, /api/positions/history, /api/engine/status
   - /api/alerts, /api/alerts/test (POST), /api/alerts/status
   - /api/backtest/stats, /api/backtest/simulate (POST), /api/backtest/export/trades, /api/backtest/export/surges
   For each, check if a dashboard page calls it via fetchAPI() or postAPI(). Flag endpoints with no frontend consumer.

2. Dashboard pages vs API calls:
   - page.tsx (Overview): calls health, balance, stats, markets/stats, ws/status, detector/stats, engine/status
   - positions/page.tsx: calls positions, positions/history
   - trades/page.tsx: calls trades (with pagination)
   - surges/page.tsx: calls surges (with pagination), surges/live
   - markets/page.tsx: calls markets (verify)
   - backtest/page.tsx: calls backtest/stats, backtest/simulate (verify)
   - settings/page.tsx: calls alerts/status, alerts/test (verify)
   Flag any pages calling endpoints not registered in api.py.

3. TypeScript types vs Python API responses -- field-by-field comparison:
   - types.ts Trade: has `max_favorable_excursion` but Python db returns `max_adverse_excursion` too (added via migration). Is max_adverse_excursion missing from TypeScript?
   - types.ts Trade: has `entry_bid`, `entry_spread`, `config_trailing_pct`, `config_max_entry`, `config_trend_min_surges` fields? These are in the trades DB table but may not be in the TypeScript type.
   - types.ts Position: Python get_open_positions() returns fields like `current_price`, `unrealized_pnl`. Are these in the TypeScript Position type?
   - types.ts WsStatus: Python get_status() returns `connections` and `tokens_per_connection`. Are these in the TypeScript WsStatus type?
   - types.ts DetectorStats: Python get_stats() returns `trending_tokens`. Is this in TypeScript?
   - types.ts Surge: Python _serialize_surge() renames `surge_magnitude` to `magnitude`. Verify TypeScript uses `magnitude` not `surge_magnitude`.
   - BacktestStats type: Python compute_stats() returns `gross_profit`, `gross_loss`, `avg_win`, `avg_loss`, etc. Compare every field against the TypeScript BacktestStats interface.
   - DailyStats type: Is this TypeScript type used anywhere? Does any API return data matching this shape?
   - BalanceEntry type: Compare against what /api/balance returns in the `history` array.

4. Missing TypeScript types:
   - Trend data: Is there a Trend type in TypeScript? The API has /api/backtest/export/surges but does it have a trends endpoint?
   - TrackedToken data: db.get_tracked_tokens() exists but is there an API endpoint for it? Is there a TypeScript type?

5. Stale type definitions:
   - After recent backend changes (trend detector, trailing stop changes), check if TypeScript types were updated accordingly.
   - SimulationResult type: Compare against simulate_params() return value. Does the simulated object include `skipped_by_threshold`?

Report: what's missing or mismatched, TypeScript location vs Python location, exact field names. Include updated JSON at end.
```

## Agent 8: DB Schema & Data Integrity

**Findings file:** `sweep_results/db_integrity.json`

```
Very thorough audit of DB schema and data integrity in the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/db_integrity.json if it exists. Follow the tracking preamble above.

The DB schema is defined in scalper/db.py _SCHEMA (lines 10-91) with migrations in _MIGRATIONS (lines 94-101).

Check:

1. FK REFERENCES:
   - trades.surge_id REFERENCES surges(id) -- but this is just a schema annotation in SQLite (not enforced by default). Is PRAGMA foreign_keys = ON ever set? If not, the FK is decorative only.
   - balance_log.trade_id REFERENCES trades(id) -- same issue.
   - Purge logic (db.py:436) nullifies trades.surge_id before deleting surges. This is correct for avoiding dangling references, but only necessary if FK enforcement is off.

2. MIGRATION SAFETY:
   - _MIGRATIONS uses bare try/except to handle "column already exists". This swallows ALL errors, including syntax errors, disk full errors, etc. A migration that fails for a real reason would be silently ignored.
   - New columns added via ALTER TABLE have no DEFAULT specified explicitly. SQLite defaults to NULL, which is fine, but verify callers handle NULL for: entry_bid, entry_spread, config_trailing_pct, config_max_entry, config_trend_min_surges, max_adverse_excursion.
   - What happens if a future migration fails partway through? There's no transaction wrapper per-migration.

3. NULLABLE COLUMNS THAT SHOULDN'T BE:
   - surges.market_name: can be NULL. Should it be NOT NULL?
   - trades.market_name: can be NULL. Same question.
   - trends.market_name: can be NULL.
   - All timestamp columns are TEXT NOT NULL -- good.
   - trades.exit_price, exit_fee, exit_time, exit_reason, pnl: these are NULL for open trades and filled on close. This is correct.
   - tracked_tokens.resolved_at: NULL for unresolved, filled when resolved. Correct.

4. MISSING INDEXES:
   - idx_price_history_token_ts exists. Good.
   - trades: No index on token_id, market_id, or exit_time. Queries like get_daily_pnl (filters by DATE(exit_time)), get_open_trades (filters by exit_time IS NULL) would benefit from indexes.
   - surges: No index on timestamp. Purge deletes by timestamp -- full table scan.
   - trends: No index on timestamp. Same issue.
   - tracked_tokens: No index on token_id or resolved_at. get_unresolved_tracked_tokens() filters by resolved_at IS NULL.
   - balance_log: No index. get_balance() orders by id DESC LIMIT 1 (uses PK). get_balance_history() same.

5. TRADE/SURGE/TREND LINKAGE INTEGRITY:
   - trade.surge_id -> surges.id: One-to-one? Or can multiple trades share a surge_id? Check if mark_surge_traded() is idempotent.
   - trends table: Has `entered` column (0/1) and `rejection_reason`. But no trade_id linking back to the specific trade that was entered. To find which trade came from which trend, you'd have to match by token_id + timestamp proximity. Is this a gap?
   - tracked_tokens: Linked by token_id. But a token can appear multiple times (tracked, resolved, tracked again). The add_tracked_token() function prevents duplicates by checking `resolved_at IS NULL`, but after resolution, the same token can be re-tracked. This is correct.

6. PURGE CORRECTNESS (db.py:429-439):
   - Deletes from price_history WHERE timestamp < cutoff.
   - Deletes from tracked_tokens WHERE resolved_at IS NOT NULL AND resolved_at < cutoff. This keeps unresolved tokens forever -- intentional?
   - Nullifies trades.surge_id WHERE surge_id IN surges with old timestamps, then deletes those surges. This means trades lose their surge link after 60 days.
   - Deletes from trends WHERE timestamp < cutoff. But if a trade was entered from this trend, the audit trail is broken.
   - Does NOT purge: trades, balance_log. These grow forever.

7. CONCURRENT ACCESS:
   - WAL mode is enabled. But with the API server and main bot running in the same process (single aiosqlite connection), all access is serialized through the single _db connection. Is this a bottleneck? aiosqlite uses a background thread for SQLite calls.
   - What if two coroutines call db.log_surge() simultaneously? aiosqlite serializes them, but the commit() after each write means transaction isolation is per-statement, not per-logical-operation.

Report: file:line, the schema/query issue, impact (data loss, broken queries, integrity violations, performance). Include updated JSON at end.
```

## Agent 9: Cross-Cutting Consistency

**Findings file:** `sweep_results/consistency.json`

```
Very thorough cross-cutting consistency audit of the Python codebase at /home/sis-magargiu-alexandru-v2/repos/polymarket-scalper/

Your job is ONLY research -- do NOT create or modify any files. Use Bash with grep/find and Read.

FINDINGS TRACKING: Before starting, read sweep_results/consistency.json if it exists. Follow the tracking preamble above.

For each domain-specific operation below, find ALL code paths that implement it. Then verify they handle edge cases identically. If one path was fixed but a parallel path wasn't, that's a finding.

Operations to audit:

1. PRICE COMPARISON CONVENTIONS (midpoint vs bid vs ask):
   - detector.py on_price_update(): Computes midpoint = (best_bid + best_ask) / 2. Uses midpoint for surge detection. Returns surge with price_at_detection = midpoint.
   - paper_engine.py on_trend(): Uses current_ask as entry_price (line 75). This is the ASK, not midpoint.
   - paper_engine.py on_price_update(): Uses midpoint for trailing stop comparison (line 202-213). But uses best_bid for exit_price (lines 215, 219).
   - paper_engine.py get_open_positions(): Uses midpoint for current_price and unrealized P&L (line 372-373).
   - tracker.py on_price_update(): Uses midpoint for resolution detection and price snapshots.
   - Find every place a price is compared, computed, or stored. Verify the convention is consistent: midpoint for detection/comparison, ask for entry, bid for exit. Or is it mixed?

2. FEE RATE APPLICATION (entry vs exit):
   - Entry fee: config.POSITION_SIZE * config.TAKER_FEE_RATE (paper_engine.py:99). This is 2% of $25 = $0.50.
   - Exit fee: pos.shares * exit_price * config.TAKER_FEE_RATE (paper_engine.py:238). This is 2% of shares * exit_price.
   - Backtest simulate_params (backtest.py:201-203): `shares * sim_exit * config.TAKER_FEE_RATE` for exit fee. Consistent with engine.
   - But entry fee in backtest (backtest.py:201): Uses `entry_fee` from the DB record. This was computed at trade time using POSITION_SIZE * TAKER_FEE_RATE. But if config changed between trade entry and backtest run, the stored fee is from the OLD config. Is this correct (historical accuracy) or a bug?
   - PnL in engine._close_position() (line 239): `(exit_price - entry_price) * shares - entry_fee - exit_fee`. Compare with PnL in backtest (line 201-203): same formula? Verify they match.
   - Balance change on exit: `proceeds = pos.shares * exit_price - exit_fee` (line 255). But the entry deducted `cost = config.POSITION_SIZE + entry_fee`. Net balance change = proceeds - cost = (shares * exit_price - exit_fee) - (POSITION_SIZE + entry_fee). Simplify: shares * exit_price - exit_fee - POSITION_SIZE - entry_fee. But POSITION_SIZE = shares * entry_price, so: shares * (exit_price - entry_price) - entry_fee - exit_fee = pnl. Verify this identity holds exactly.

3. DIRECTION HANDLING:
   - Direction.UP and Direction.DOWN are defined in models.py. But the bot ONLY trades Direction.UP:
     - paper_engine.py on_trend() (line 106): Always sets direction=Direction.UP.
     - detector.py _check_surge() (line 88): Always creates surge with direction=Direction.UP (only detects upward moves: magnitude = midpoint - min_point.midpoint).
   - But Direction.DOWN exists in the codebase. Is it ever used?
     - telegram.py: send_entry() and send_exit() check for Direction.DOWN in format strings.
     - backtest.py simulate_params(): Has a full `else` branch for direction == "down" (lines 206-214). This code is dead since no trades are ever created with direction=down.
   - Is bidirectional trading (spec says "ride up AND down") planned but not implemented? Or was it removed? If removed, the DOWN code paths should be cleaned up.

4. TIMESTAMP FORMATS (unix vs ISO):
   - Internal Python code uses UNIX timestamps (float seconds): detector, paper_engine, main.py event timestamps.
   - DB storage uses ISO 8601 strings: db._ts_to_iso() converts unix -> ISO for all DB writes.
   - API responses: Some return raw DB rows (ISO strings), some compute values from engine state (which uses unix timestamps, but converts to ISO via datetime.fromtimestamp().isoformat() in get_open_positions).
   - websocket.py: Converts Polymarket timestamps from milliseconds to seconds (/ 1000).
   - Is there any path where a unix timestamp is stored as-is in the DB (without ISO conversion)? Or an ISO string is compared as a number?
   - balance_log.timestamp uses _now_iso() (current time) rather than trade timestamp. This means the balance_log timestamp might differ from the trade's entry_time/exit_time if there's any delay.

5. POSITION SIZE CALCULATIONS:
   - Shares = POSITION_SIZE / entry_price (paper_engine.py:98). This means shares vary per trade based on entry price.
   - Exit proceeds = shares * exit_price (paper_engine.py:255). This can be more or less than POSITION_SIZE depending on price movement.
   - But is POSITION_SIZE always $25? Or can it vary? Check if any code path sets position_size to anything other than config.POSITION_SIZE.
   - Rounding: shares is float (no rounding at entry). Polymarket actually requires integer share counts. Does the paper engine need to round?

6. SPREAD AND RESOLVING MARKET DETECTION:
   - paper_engine.py on_trend() (line 77): `current_bid < 0.02 or current_ask > 0.98` -- resolving market check.
   - tracker.py (line 48): `bid < RESOLUTION_BID or ask > RESOLUTION_ASK` where RESOLUTION_BID=0.02, RESOLUTION_ASK=0.98.
   - detector.py: No resolving market check. Surges can fire on resolving markets.
   - paper_engine.py on_trend() (line 87-89): `spread > 0.15` -- wide spread check. But on_price_update() (the exit path) has NO spread check. A position could be exited at a terrible price in a wide-spread market.
   - Are the resolving market thresholds (0.02/0.98) consistent everywhere? What about markets that hover at 0.03 or 0.97?

For each finding: list the "reference" implementation (the intended behavior) and the "inconsistent" implementation (the one that diverges), exact code locations (file:line), what the difference is, and whether it looks intentional or accidental. Include updated JSON at end.
```

---

## Presenting Results

After all 9 agents complete:

1. **Verify critical findings** -- grep/read the actual code before reporting. Agents hallucinate file paths and line numbers.
2. **Dismiss false positives** -- check if "dead" functions have callers the agent missed, if "unreachable" code is actually reachable.
3. **Check regressions** -- any finding marked REGRESSION means a previous fix was reverted. These are P0.
4. **Prioritize** -- regressions > bugs > missed trades > logging gaps > config drift
5. **Present to user** as a single consolidated list grouped by priority:
   - **P0 (critical)**: Regressions, logic errors, missed trade data, memory leaks, DB integrity issues
   - **P1 (gaps)**: Logging holes, missed trade pipeline gaps, dashboard blind spots, fee inconsistencies
   - **P2 (cleanup)**: Dead code, unused types, unused config params, stale TypeScript types
   - **P3 (drift)**: Config/code drift, hardcoded values, naming inconsistencies, Direction.DOWN dead paths
6. **Update findings files** -- after reviewing with the user, write the updated JSON arrays to `sweep_results/*.json`. Set status for each finding: `fixed`, `false_positive`, `wont_fix`, or leave as `open`.
