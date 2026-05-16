# CLAUDE.md

## Project Overview

Polymarket momentum scalping bot. Detects price surges across all active markets via WebSocket and rides them with a trailing stop.

Full specification: `SPEC.md`
Supervisor prompt: `SUPERVISOR_PROMPT.md`

## Tech Stack

- Python 3.11+ (asyncio)
- `py-clob-client` — official Polymarket CLOB SDK
- `websockets` or `aiohttp` — WebSocket connections
- SQLite — trade log and metrics
- Deployed on Hetzner VPS (Finland)

## Commands

```bash
# Run observer (Phase 1)
python3 -m scalper.observer

# Run paper trading (Phase 2)
python3 -m scalper.paper

# Run live (Phase 3+)
python3 -m scalper.live

# Run tests
pytest tests/

# Install dependencies
pip install -r requirements.txt
```

## Project Structure (planned)

```
scalper/
├── __init__.py
├── observer.py        # Phase 1: WebSocket → log surges
├── paper.py           # Phase 2: Simulated trading
├── live.py            # Phase 3+: Real execution
├── websocket.py       # WebSocket connection manager
├── detector.py        # Surge detection logic
├── executor.py        # CLOB order placement
├── positions.py       # Position tracking + trailing stops
├── markets.py         # Market discovery + filtering
├── config.py          # Parameters + env vars
└── db.py              # SQLite trade log
tests/
├── test_detector.py
├── test_positions.py
└── test_executor.py
```

## Behavioral Guidelines

- Start with observer (no money at risk)
- Never exceed position limits
- Always have a trailing stop — no "hope" trades
- Log everything — every surge, every entry, every exit
- Exit on disconnect — if WebSocket drops, close all positions
