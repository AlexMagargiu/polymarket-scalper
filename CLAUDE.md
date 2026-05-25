# CLAUDE.md

## Project Overview

Polymarket momentum scalping bot. Detects price surges (up AND down) across all active markets via WebSocket and rides them with a trailing stop. Currently building paper trading implementation.

Full specification: `SPEC.md`
Implementation plan: `IMPLEMENTATION_PLAN.md`
Supervisor prompt: `SUPERVISOR_PROMPT.md`

## Tech Stack

### Bot
- Python 3.12+ (asyncio)
- `websockets` — WebSocket connection to Polymarket CLOB
- `aiohttp` — HTTP client for Gamma API + REST API server for dashboard
- `aiosqlite` — async SQLite for trade logging
- `python-telegram-bot` — Telegram alerts

### Dashboard (same conventions as weather-arb/dashboard/)
- Next.js (App Router, TypeScript, Tailwind v4)
- TanStack Query v5 (useQuery, 30s refetch)
- Base-UI + CVA compound components, lightweight-charts
- API proxy: `/api/[...path]/route.ts` -> VPS bot API
- Auth: JWT (jose) with login page + middleware
- Deployed on Vercel

### Deployment
- Bot: Hetzner VPS (Finland, 8GB RAM), systemd service
- Dashboard: Vercel, API proxy to VPS

## Commands

```bash
# Run paper trading bot
python3 -m scalper

# Run backtest / stats
python3 -m scalper.backtest --stats
python3 -m scalper.backtest --export
python3 -m scalper.backtest --simulate --threshold 0.15 --trailing 0.08

# Run tests
pytest tests/

# Install bot dependencies
pip install -r requirements.txt

# Dashboard
cd dashboard && npm install
cd dashboard && npm run dev    # dev server
cd dashboard && npm run build  # production build
```

## Project Structure

```
scalper/
├── __init__.py
├── __main__.py        # Entry point
├── main.py            # Asyncio orchestration
├── config.py          # Parameters + env vars
├── models.py          # Dataclasses (Market, Surge, Position, Trade)
├── db.py              # SQLite trade log + queries
├── api.py             # JSON REST API for dashboard
├── markets.py         # Gamma API market discovery
├── websocket.py       # WebSocket connection manager
├── detector.py        # Surge detection (rolling windows)
├── paper_engine.py    # Paper trading (entries, exits, P&L)
├── telegram.py        # Telegram alerts
└── backtest.py        # Trade export + parameter simulation
dashboard/
├── app/               # Next.js App Router pages
├── lib/api.ts         # Bot API client
└── types/index.ts     # TypeScript types
tests/
├── test_detector.py
├── test_paper_engine.py
├── test_db.py
├── test_markets.py
├── test_websocket.py
└── test_models.py
```

## Key Parameters

- Surge threshold: 10c in 30-60s
- Trailing stop: 10c reversal from peak
- Take profit: hard exit at 90c
- Position size: $25, budget $5,000
- Fees: simulate 2% taker both sides
- Bidirectional: ride up (buy YES) and down (buy NO)
- Markets: all active with $10K+ 24h volume

## VPS Database Schema (actual column names on live DB)

The VPS DB was created before some code refactors — column names differ from what the code defines. Always check these before querying:

- **trades**: `market_name` (not `question`), `pnl` (not `net_pnl`), no `trade_id` column in `trends` table yet (migration needed)
- **surges**: `surge_magnitude` (not `magnitude`)
- **trends**: `rejection_reason` (not `reason`), columns: `id, timestamp, token_id, market_id, market_name, surge_count, first_surge_price, current_price, window_seconds, entered, rejection_reason, entry_bid, entry_ask`
- **trades columns**: `id, surge_id, market_id, token_id, market_name, direction, entry_price, entry_fee, entry_time, exit_price, exit_fee, exit_time, exit_reason, pnl, shares, position_cost, peak_price, max_favorable_excursion, entry_bid, entry_spread, config_trailing_pct, config_max_entry, config_trend_min_surges, max_adverse_excursion, config_surge_threshold, config_taker_fee_rate, config_position_size`
- **VPS has no `sqlite3` CLI** — use `venv/bin/python3 -c "import sqlite3; ..."` instead
- **Bot restarted with v6 code on 2026-05-22 20:29 UTC** — trades before that used older parameters/no sports filter

## Behavioral Guidelines

- Never exceed position limits (10 concurrent, 3 per market, $25 each)
- Always have a trailing stop — no "hope" trades
- Log everything — every surge, every entry, every exit
- Exit on disconnect — if WebSocket drops >30s, close all positions
- Daily loss limit $500 — pause trading if hit
- Hard exit at 90c — protect against sudden reversals near resolution
