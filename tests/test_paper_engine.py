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


@pytest.mark.asyncio
async def test_successful_entry(engine):
    trend = _make_trend(first_surge_price=0.10, current_price=0.30)
    pos, rejection = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)

    assert pos is not None
    assert rejection is None
    assert pos.direction == Direction.UP
    assert pos.entry_price == 0.31
    assert pos.shares == pytest.approx(config.POSITION_SIZE / 0.31, rel=0.01)
    assert pos.entry_fee == pytest.approx(config.POSITION_SIZE * config.TAKER_FEE_RATE)

    status = engine.get_status()
    assert status["balance"] < config.STARTING_BALANCE
    assert status["open_positions"] == 1


@pytest.mark.asyncio
async def test_entry_rejected_insufficient_balance(engine):
    engine._balance = 10.0
    trend = _make_trend()
    pos, rejection = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert rejection is not None


@pytest.mark.asyncio
async def test_entry_rejected_max_concurrent(engine):
    for i in range(config.MAX_CONCURRENT_POSITIONS):
        trend = _make_trend(
            token_id=f"tok_{i}",
            market_id=f"cond_{i}",
            market_name=f"Market {i}",
        )
        pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
        assert pos is not None

    trend = _make_trend(token_id="tok_extra", market_id="cond_extra")
    pos, rejection = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert rejection is not None


@pytest.mark.asyncio
async def test_entry_rejected_resolving_market(engine):
    # bid near 0 — resolving
    trend = _make_trend(current_price=0.01)
    pos, _ = await engine.on_trend(trend, current_bid=0.01, current_ask=0.03)
    assert pos is None

    # ask near 1 — resolving
    trend = _make_trend(current_price=0.98)
    pos, _ = await engine.on_trend(trend, current_bid=0.96, current_ask=0.99)
    assert pos is None


@pytest.mark.asyncio
async def test_trailing_stop_exit(engine):
    trend = _make_trend(first_surge_price=0.05, current_price=0.25)
    pos, _ = await engine.on_trend(trend, current_bid=0.24, current_ask=0.26)
    assert pos is not None
    token_id = pos.token_id

    # entry at 0.26 (ask), trailing_peak = midpoint 0.25
    # peak becomes 0.40 (midpoint of 0.39/0.41)
    # 10% of 0.40 = 0.04 drop needed → trigger at 0.36
    closed = await engine.on_price_update(token_id, 0.39, 0.41, time.time() + 35)
    assert len(closed) == 0

    # midpoint 0.37 → (0.40-0.37)/0.40 = 7.5% < 10% → no trigger
    closed = await engine.on_price_update(token_id, 0.36, 0.38, time.time() + 40)
    assert len(closed) == 0

    # midpoint 0.35 → (0.40-0.35)/0.40 = 12.5% >= 10% → trigger (past 30s grace)
    closed = await engine.on_price_update(token_id, 0.34, 0.36, time.time() + 45)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TRAILING_STOP
    assert closed[0].exit_price == 0.34
    assert closed[0].peak_price == pytest.approx(0.40, abs=0.01)


@pytest.mark.asyncio
async def test_take_profit_exit(engine):
    trend = _make_trend(first_surge_price=0.05, current_price=0.25)
    pos, _ = await engine.on_trend(trend, current_bid=0.24, current_ask=0.26)
    token_id = pos.token_id

    closed = await engine.on_price_update(token_id, 0.90, 0.92, time.time() + 60)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TAKE_PROFIT


@pytest.mark.asyncio
async def test_pnl_calculation_with_fees(engine):
    trend = _make_trend(first_surge_price=0.05, current_price=0.25)
    pos, _ = await engine.on_trend(trend, current_bid=0.24, current_ask=0.25)
    assert pos is not None

    entry_price = 0.25
    shares = config.POSITION_SIZE / entry_price
    entry_fee = config.POSITION_SIZE * config.TAKER_FEE_RATE

    # Peak at midpoint 0.45; 10% of 0.45 = 0.045 → stop at 0.405
    # Exit at bid=0.39 (midpoint 0.40 < 0.405)
    exit_price = 0.39
    exit_fee = shares * exit_price * config.TAKER_FEE_RATE
    expected_pnl = (exit_price - entry_price) * shares - entry_fee - exit_fee

    await engine.on_price_update(pos.token_id, 0.44, 0.46, time.time() + 35)
    closed = await engine.on_price_update(pos.token_id, 0.39, 0.41, time.time() + 40)

    assert len(closed) == 1
    assert closed[0].pnl == pytest.approx(expected_pnl, abs=0.05)


@pytest.mark.asyncio
async def test_multiple_positions_same_market(engine, monkeypatch):
    monkeypatch.setattr(config, "MAX_ENTRIES_PER_MARKET_PER_DAY", config.MAX_POSITIONS_PER_MARKET + 1)
    for i in range(config.MAX_POSITIONS_PER_MARKET):
        trend = _make_trend(timestamp=time.time() + i * 61)
        pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
        assert pos is not None

    trend = _make_trend(timestamp=time.time() + 200)
    pos, rejection = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert rejection is not None
    assert engine.get_status()["open_positions"] == config.MAX_POSITIONS_PER_MARKET


@pytest.mark.asyncio
async def test_daily_loss_limit_pauses(engine):
    from datetime import datetime, timezone

    engine._daily_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._daily_pnl = -(config.DAILY_LOSS_LIMIT + 1)

    trend = _make_trend()
    pos, rejection = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert rejection is not None
    assert engine.get_status()["paused"] is True


@pytest.mark.asyncio
async def test_recovery_restores_daily_counters(tmp_path):
    path = str(tmp_path / "test.db")
    await db.init_db(path)

    eng1 = PaperEngine()
    await eng1.init()

    # Open a position and close it with known P&L
    trend = _make_trend(first_surge_price=0.05, current_price=0.25)
    pos, _ = await eng1.on_trend(trend, current_bid=0.24, current_ask=0.25)
    assert pos is not None

    # Peak at 0.45, 10% of 0.45 = 0.045 → stop at 0.405; midpoint 0.40 triggers
    await eng1.on_price_update(pos.token_id, 0.44, 0.46, time.time() + 35)
    closed = await eng1.on_price_update(pos.token_id, 0.39, 0.41, time.time() + 40)
    assert len(closed) == 1

    saved_pnl = eng1._daily_pnl
    saved_trades = eng1._daily_trades
    assert saved_trades == 1
    assert saved_pnl != 0

    # Simulate restart — new engine, same DB
    eng2 = PaperEngine()
    await eng2.init()

    assert eng2._daily_trades == saved_trades
    assert eng2._daily_pnl == pytest.approx(saved_pnl, abs=0.01)

    await db.close_db()


@pytest.mark.asyncio
async def test_disconnect_closes_all(engine):
    for i in range(3):
        trend = _make_trend(
            token_id=f"tok_{i}", market_id=f"cond_{i}", market_name=f"Market {i}"
        )
        pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
        assert pos is not None
        engine._last_prices[f"tok_{i}"] = (0.35, 0.37)

    assert engine.get_status()["open_positions"] == 3

    closed = await engine.on_disconnect()
    assert len(closed) == 3
    assert all(t.exit_reason == ExitReason.DISCONNECT for t in closed)
    assert engine.get_status()["open_positions"] == 0


@pytest.mark.asyncio
async def test_trailing_stop_percentage(engine):
    trend = _make_trend(first_surge_price=0.10, current_price=0.30)
    pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is not None

    # peak at midpoint 0.50; 10% of 0.50 = 0.05 → stop at 0.45
    closed = await engine.on_price_update("tok_yes", 0.49, 0.51, time.time() + 35)
    assert closed == []

    # midpoint 0.46 → (0.50-0.46)/0.50 = 8% < 10% → no trigger
    closed = await engine.on_price_update("tok_yes", 0.45, 0.47, time.time() + 40)
    assert closed == []

    # midpoint 0.44 → (0.50-0.44)/0.50 = 12% >= 10% → trigger
    closed = await engine.on_price_update("tok_yes", 0.43, 0.45, time.time() + 45)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TRAILING_STOP
    assert closed[0].exit_price == 0.43


@pytest.mark.asyncio
async def test_trailing_stop_grace_period(engine):
    now = time.time()
    trend = _make_trend(first_surge_price=0.10, current_price=0.30, timestamp=now)
    pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is not None

    # Price drops 15% immediately — within grace period, should NOT trigger
    closed = await engine.on_price_update("tok_yes", 0.20, 0.22, now + 5)
    assert closed == []

    # Still within grace period at 25s
    closed = await engine.on_price_update("tok_yes", 0.20, 0.22, now + 25)
    assert closed == []

    # Past grace period (31s) — NOW it should trigger
    closed = await engine.on_price_update("tok_yes", 0.20, 0.22, now + 31)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TRAILING_STOP


@pytest.mark.asyncio
async def test_entry_rejected_max_entry_price(engine):
    trend = _make_trend(current_price=0.85)
    pos, _ = await engine.on_trend(trend, current_bid=0.84, current_ask=0.86)
    assert pos is None


@pytest.mark.asyncio
async def test_entry_rejected_weak_magnitude(engine):
    trend = _make_trend(first_surge_price=0.40, current_price=0.45)
    pos, rejection = await engine.on_trend(trend, current_bid=0.44, current_ask=0.46)
    assert pos is None
    assert "weak trend magnitude" in rejection


@pytest.mark.asyncio
async def test_entry_accepted_strong_magnitude(engine):
    trend = _make_trend(first_surge_price=0.40, current_price=0.57)
    pos, rejection = await engine.on_trend(trend, current_bid=0.56, current_ask=0.58)
    assert pos is not None
    assert rejection is None


@pytest.mark.asyncio
async def test_daily_market_limit(engine):
    trend1 = _make_trend(market_id="cond_limit", token_id="tok_limit")
    pos, rejection = await engine.on_trend(trend1, current_bid=0.39, current_ask=0.41)
    assert pos is not None

    trend2 = _make_trend(market_id="cond_limit", token_id="tok_limit", timestamp=time.time() + 60)
    pos, rejection = await engine.on_trend(trend2, current_bid=0.39, current_ask=0.41)
    assert pos is None
    assert "max daily entries for this market" in rejection


@pytest.mark.asyncio
async def test_daily_market_limit_resets_on_new_day(engine):
    trend1 = _make_trend(market_id="cond_reset", token_id="tok_reset")
    pos, _ = await engine.on_trend(trend1, current_bid=0.39, current_ask=0.41)
    assert pos is not None

    # Close the position so MAX_POSITIONS_PER_MARKET doesn't block
    closed = await engine.on_price_update("tok_reset", 0.90, 0.92, time.time() + 60)
    assert len(closed) == 1

    # Simulate day change
    engine._daily_date = "1999-01-01"
    engine._check_daily_reset()

    trend2 = _make_trend(market_id="cond_reset", token_id="tok_reset", timestamp=time.time() + 120)
    pos, rejection = await engine.on_trend(trend2, current_bid=0.39, current_ask=0.41)
    assert pos is not None
    assert rejection is None


@pytest.mark.asyncio
async def test_entry_rejected_reversed_trend(engine):
    trend = _make_trend(first_surge_price=0.50, current_price=0.40)
    pos, rejection = await engine.on_trend(trend, current_bid=0.39, current_ask=0.41)
    assert pos is None
    assert "reversed trend" in rejection


@pytest.mark.asyncio
async def test_daily_market_limit_survives_restart(tmp_path):
    path = str(tmp_path / "test.db")
    await db.init_db(path)

    eng1 = PaperEngine()
    await eng1.init()

    trend = _make_trend(market_id="cond_persist", token_id="tok_persist")
    pos, _ = await eng1.on_trend(trend, current_bid=0.39, current_ask=0.41)
    assert pos is not None

    # Simulate restart — new engine, same DB
    eng2 = PaperEngine()
    await eng2.init()

    assert eng2._daily_market_entries.get("cond_persist", 0) >= 1

    trend2 = _make_trend(market_id="cond_persist", token_id="tok_persist", timestamp=time.time() + 60)
    pos, rejection = await eng2.on_trend(trend2, current_bid=0.39, current_ask=0.41)
    assert pos is None
    assert "max daily entries for this market" in rejection

    await db.close_db()


@pytest.mark.asyncio
async def test_stale_position_closed(engine):
    trend = _make_trend(first_surge_price=0.10, current_price=0.30)
    now = time.time()
    pos, _ = await engine.on_trend(trend, current_bid=0.29, current_ask=0.31)
    assert pos is not None

    await engine.on_price_update("tok_yes", 0.34, 0.36, now + 10)

    closed = await engine.close_stale_positions(now + 100)
    assert len(closed) == 0

    closed = await engine.close_stale_positions(now + config.STALE_POSITION_TIMEOUT + 20)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.DISCONNECT
