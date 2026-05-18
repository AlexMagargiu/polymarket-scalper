import pytest
import pytest_asyncio
import time

from scalper import db, config
from scalper.models import Surge, Direction, ExitReason
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


@pytest.mark.asyncio
async def test_successful_entry(engine):
    surge = _make_surge(direction=Direction.UP, price=0.30)
    pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)

    assert pos is not None
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
    surge = _make_surge()
    pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
    assert pos is None


@pytest.mark.asyncio
async def test_entry_rejected_max_concurrent(engine):
    for i in range(config.MAX_CONCURRENT_POSITIONS):
        surge = _make_surge(
            token_id=f"tok_{i}",
            market_id=f"cond_{i}",
            market_name=f"Market {i}",
        )
        pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
        assert pos is not None

    surge = _make_surge(token_id="tok_extra", market_id="cond_extra")
    pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
    assert pos is None


@pytest.mark.asyncio
async def test_entry_rejected_price_out_of_bounds(engine):
    surge = _make_surge(direction=Direction.UP, price=0.50)
    pos = await engine.on_surge(surge, current_bid=0.49, current_ask=0.51)
    assert pos is None

    surge = _make_surge(direction=Direction.DOWN, price=0.40)
    pos = await engine.on_surge(surge, current_bid=0.39, current_ask=0.41)
    assert pos is None


@pytest.mark.asyncio
async def test_trailing_stop_exit(engine):
    surge = _make_surge(direction=Direction.UP, price=0.25)
    pos = await engine.on_surge(surge, current_bid=0.24, current_ask=0.26)
    assert pos is not None
    token_id = pos.token_id

    closed = await engine.on_price_update(token_id, 0.39, 0.41, time.time() + 10)
    assert len(closed) == 0

    closed = await engine.on_price_update(token_id, 0.34, 0.36, time.time() + 20)
    assert len(closed) == 0

    closed = await engine.on_price_update(token_id, 0.29, 0.31, time.time() + 30)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TRAILING_STOP
    assert closed[0].exit_price == 0.29
    assert closed[0].peak_price == pytest.approx(0.40, abs=0.01)


@pytest.mark.asyncio
async def test_take_profit_exit(engine):
    surge = _make_surge(direction=Direction.UP, price=0.25)
    pos = await engine.on_surge(surge, current_bid=0.24, current_ask=0.26)
    token_id = pos.token_id

    closed = await engine.on_price_update(token_id, 0.90, 0.92, time.time() + 60)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.TAKE_PROFIT


@pytest.mark.asyncio
async def test_pnl_calculation_with_fees(engine):
    surge = _make_surge(direction=Direction.UP, price=0.25)
    pos = await engine.on_surge(surge, current_bid=0.24, current_ask=0.25)
    assert pos is not None

    entry_price = 0.25
    shares = config.POSITION_SIZE / entry_price
    entry_fee = config.POSITION_SIZE * config.TAKER_FEE_RATE

    # Exit at bid=0.34 (trailing stop triggers when midpoint drops 10c from peak of 0.45)
    exit_price = 0.34
    exit_fee = shares * exit_price * config.TAKER_FEE_RATE
    expected_pnl = (exit_price - entry_price) * shares - entry_fee - exit_fee

    await engine.on_price_update(pos.token_id, 0.44, 0.46, time.time() + 10)
    closed = await engine.on_price_update(pos.token_id, 0.34, 0.36, time.time() + 20)

    assert len(closed) == 1
    assert closed[0].pnl == pytest.approx(expected_pnl, abs=0.05)


@pytest.mark.asyncio
async def test_multiple_positions_same_market(engine):
    for i in range(config.MAX_POSITIONS_PER_MARKET):
        surge = _make_surge(timestamp=time.time() + i * 61)
        pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
        assert pos is not None

    surge = _make_surge(timestamp=time.time() + 200)
    pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert engine.get_status()["open_positions"] == config.MAX_POSITIONS_PER_MARKET


@pytest.mark.asyncio
async def test_daily_loss_limit_pauses(engine):
    from datetime import datetime, timezone

    engine._daily_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._daily_pnl = -(config.DAILY_LOSS_LIMIT + 1)

    surge = _make_surge()
    pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
    assert pos is None
    assert engine.get_status()["paused"] is True


@pytest.mark.asyncio
async def test_recovery_restores_daily_counters(tmp_path):
    path = str(tmp_path / "test.db")
    await db.init_db(path)

    eng1 = PaperEngine()
    await eng1.init()

    # Open a position and close it with known P&L
    surge = _make_surge(direction=Direction.UP, price=0.25)
    pos = await eng1.on_surge(surge, current_bid=0.24, current_ask=0.25)
    assert pos is not None

    # Exit with trailing stop (peak at 0.45, drop to 0.35)
    await eng1.on_price_update(pos.token_id, 0.44, 0.46, time.time() + 10)
    closed = await eng1.on_price_update(pos.token_id, 0.34, 0.36, time.time() + 20)
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
        surge = _make_surge(
            token_id=f"tok_{i}", market_id=f"cond_{i}", market_name=f"Market {i}"
        )
        pos = await engine.on_surge(surge, current_bid=0.29, current_ask=0.31)
        assert pos is not None
        engine._last_prices[f"tok_{i}"] = (0.35, 0.37)

    assert engine.get_status()["open_positions"] == 3

    closed = await engine.on_disconnect()
    assert len(closed) == 3
    assert all(t.exit_reason == ExitReason.DISCONNECT for t in closed)
    assert engine.get_status()["open_positions"] == 0
