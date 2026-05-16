# Polymarket Momentum Scalper — Specification

## Concept

A bot that monitors ALL active Polymarket markets via WebSocket, detects price surges (rapid directional moves), enters positions to ride the momentum, and exits when momentum fades. Pure momentum following — no prediction model, no fundamentals, just price action.

---

## Core Strategy

```
FOR EACH MARKET:
  WATCH:   Track price via WebSocket (real-time order book updates)
  DETECT:  Price moves +X¢ from its rolling low within Y seconds
  ENTER:   Buy YES (or NO if dropping) at market via limit order
  RIDE:    Track trailing high/low while position is open
  EXIT:    When price reverses Z¢ from trailing extreme → sell
```

### Parameters (starting point, to be tuned)

| Parameter | Initial Value | Notes |
|-----------|--------------|-------|
| Surge threshold | +15¢ | Minimum move to trigger entry |
| Detection window | 30-60 seconds | How fast the move must happen |
| Max entry price | $0.40 | Don't enter above this (breakeven too high) |
| Min entry price | $0.10 | Below this, liquidity is likely zero |
| Trailing stop | -5¢ from peak | Exit trigger |
| Max hold time | 10 minutes | Force exit if no resolution |
| Min volume (24h) | $5,000 | Skip illiquid markets |
| Position size | $25-50 | Per trade |

### Entry Conditions (ALL must be true)

1. Price moved +15¢ from 30s rolling low
2. Current price ≤ $0.40 (for YES side) or ≥ $0.60 (for NO side surges)
3. Market has had $5K+ volume in last 24h
4. No existing position in this market
5. Total open positions < max_concurrent (e.g., 5)

### Exit Conditions (ANY triggers exit)

1. Price drops 5¢ from trailing high (profit-taking / stop-loss)
2. Hold time exceeds 10 minutes (timeout)
3. Price hits $0.90+ (take full profit, don't wait for reversal)

---

## Architecture

```
┌─────────────────────────────────────────┐
│           WebSocket Manager             │
│  - Subscribes to all active markets     │
│  - Receives real-time price updates     │
│  - Maintains per-market price windows   │
└──────────────┬──────────────────────────┘
               │ price events
               ▼
┌─────────────────────────────────────────┐
│           Surge Detector                │
│  - Rolling window per market (30-60s)   │
│  - Computes price delta from low        │
│  - Fires SURGE event when threshold hit │
└──────────────┬──────────────────────────┘
               │ surge signals
               ▼
┌─────────────────────────────────────────┐
│         Position Manager                │
│  - Validates entry conditions           │
│  - Places limit buy order               │
│  - Tracks trailing high per position    │
│  - Triggers exit on reversal/timeout    │
└──────────────┬──────────────────────────┘
               │ orders
               ▼
┌─────────────────────────────────────────┐
│         CLOB Executor                   │
│  - Polymarket CLOB API client           │
│  - Places/cancels limit orders          │
│  - Confirms fills                       │
│  - Handles partial fills                │
└─────────────────────────────────────────┘
```

### Technology

- **Language**: Python (asyncio) — fast development, good WebSocket libraries, Polymarket has official Python SDK (`py-clob-client`)
- **WebSocket**: `websockets` or `aiohttp` for real-time CLOB data feed
- **Execution**: Polymarket `py-clob-client` for order placement
- **State**: In-memory (positions, price windows). SQLite for trade log.
- **Deployment**: Same VPS (Finland, Hetzner). ~30-40ms to Polymarket London servers.

---

## Polymarket Integration

### Data Feed (WebSocket)

Polymarket CLOB WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market`

Subscribe to market price updates. Each message contains:
- Market ID / condition ID
- Best bid / best ask
- Last trade price
- Timestamp

### Market Discovery

Gamma API: `https://gamma-api.polymarket.com/markets`
- Fetch all active markets
- Filter by: active=true, volume > threshold, not closed
- Refresh market list every 5-10 minutes

### Order Execution

CLOB API: `https://clob.polymarket.com`
- POST `/order` — place limit order
- DELETE `/order/{id}` — cancel
- GET `/orders` — check fills
- Requires: API key + API secret + wallet signature (EIP-712)

### Requirements

- **Polymarket API credentials** (API key + secret)
- **Funded wallet** (USDC on Polygon) for trading
- **Approval/allowance** set for CLOB contract

---

## Risk Management

| Risk | Mitigation |
|------|-----------|
| Flash crash / manipulation | Max position size cap, max concurrent positions |
| Liquidity disappears on exit | Place limit sell (not market), accept wider trailing stop in thin markets |
| Rapid losing streak | Daily loss limit ($200?), pause trading if hit |
| API rate limits | Respect rate limits, prioritize high-volume markets |
| WebSocket disconnection | Auto-reconnect with exponential backoff, close all positions on prolonged disconnect |
| Stale data | Heartbeat check — if no update in 30s for subscribed market, assume stale |

### Position Limits

- Max concurrent positions: 5
- Max single position: $50
- Max daily loss: $200
- Max daily trades: 50

---

## Fees

| Action | Fee |
|--------|-----|
| Limit order (maker) | 0% + potentially rebate |
| Market order (taker) | ~2% |
| Cancel | Free |

**Strategy:** Enter via aggressive limit order (1¢ above best bid) to get maker fee. Exit via limit order at trailing_high - 5¢. If exit not filled within 30s, cross the spread (taker).

---

## Metrics & Logging

Track per trade:
- Market (name, ID, category)
- Entry price, exit price, P&L
- Hold duration
- Surge magnitude at entry (how much had it moved before we entered)
- Max favorable excursion (how much higher did it go after entry)
- Slippage (intended entry vs actual fill)

Aggregate:
- Win rate, avg win, avg loss
- Sharpe ratio (daily)
- Max drawdown
- Trades per day, by market category

---

## Development Phases

### Phase 1: Observer (no trading)
- Connect to WebSocket
- Subscribe to top 100 markets by volume
- Log all surge events (15¢+ in 60s)
- Record: market, time, surge magnitude, subsequent price action (did it continue or reverse?)
- Duration: 3-5 days
- Goal: Validate signal frequency and quality

### Phase 2: Paper Trading
- Same as Phase 1 but simulate entries/exits
- Calculate paper P&L
- Tune parameters (surge threshold, trailing stop, max hold time)
- Duration: 1-2 weeks
- Goal: Positive paper P&L with acceptable drawdown

### Phase 3: Live (Small Size)
- Real orders, $10-25 positions
- Manual monitoring first 48h
- Telegram alerts on every trade
- Duration: 1 week
- Goal: Verify execution matches paper results

### Phase 4: Scale
- Increase to $50 positions
- Add more markets (beyond top 100)
- Optimize order placement (maker vs taker)
- Consider bidirectional (ride surges AND drops)

---

## Open Questions (Discuss with Supervisor)

1. **Bidirectional?** Should we also short (buy NO) on price drops? Or only ride surges up?
2. **Market filtering:** Only high-volume ($10K+/day)? Or also catch opportunities in $2-5K markets?
3. **Category focus:** Equal weight all categories? Or prioritize weather/sports (daily resolution = more frequent moves)?
4. **Entry method:** Market order (guaranteed fill, pays taker fee) vs limit order (free but might miss)?
5. **Multiple positions same market?** Scale in on continued surge, or one shot only?
6. **Holding overnight?** If a position is +10¢ but hasn't hit the trailing stop, do we hold or force-close end of day?
7. **Correlation risk:** If 5 positions are all "election" category, one news event could reverse all of them simultaneously.
