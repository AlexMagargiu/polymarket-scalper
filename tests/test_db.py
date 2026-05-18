import pytest
import pytest_asyncio
from datetime import datetime, timezone

from scalper import db
from scalper.models import Surge, Trade, Direction, ExitReason


@pytest_asyncio.fixture
async def test_db(tmp_path):
    path = str(tmp_path / "test.db")
    await db.init_db(path)
    yield
    await db.close_db()


def _make_surge(ts: float = 1700000000.0, direction: Direction = Direction.UP, magnitude: float = 0.12) -> Surge:
    return Surge(
        market_id="cond_abc",
        token_id="tok_yes",
        market_name="Will X happen?",
        direction=direction,
        magnitude=magnitude,
        window_seconds=45.0,
        price_at_detection=0.35,
        timestamp=ts,
    )


def _make_trade(surge_id: int = None, entry_time: float = 1700000010.0, direction: Direction = Direction.UP) -> Trade:
    return Trade(
        surge_id=surge_id,
        market_id="cond_abc",
        token_id="tok_yes",
        market_name="Will X happen?",
        direction=direction,
        entry_price=0.35,
        entry_fee=0.50,
        entry_time=entry_time,
        shares=71.43,
        position_size=25.0,
    )


@pytest.mark.asyncio
async def test_init_creates_tables(test_db):
    conn = await db.get_db()
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in await cursor.fetchall()]
    assert "balance_log" in tables
    assert "surges" in tables
    assert "trades" in tables

    balance = await db.get_balance()
    assert balance == 5000.0


@pytest.mark.asyncio
async def test_log_surge_and_retrieve(test_db):
    surge = _make_surge()
    surge_id = await db.log_surge(surge)
    assert surge_id is not None and surge_id > 0

    surges = await db.get_all_surges()
    assert len(surges) == 1
    s = surges[0]
    assert s["market_id"] == "cond_abc"
    assert s["direction"] == "up"
    assert s["surge_magnitude"] == 0.12
    assert s["traded"] == 0


@pytest.mark.asyncio
async def test_log_trade_entry_and_exit(test_db):
    surge = _make_surge()
    surge_id = await db.log_surge(surge)

    trade = _make_trade(surge_id=surge_id)
    trade_id = await db.log_trade_entry(trade)
    assert trade_id is not None and trade_id > 0

    surges = await db.get_all_surges()
    assert surges[0]["traded"] == 1

    await db.log_trade_exit(
        trade_id=trade_id,
        exit_price=0.42,
        exit_fee=0.50,
        exit_time=1700000070.0,
        exit_reason=ExitReason.TRAILING_STOP,
        pnl=4.00,
        peak_price=0.45,
        max_favorable=0.10,
    )

    trades = await db.get_all_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t["exit_price"] == 0.42
    assert t["exit_reason"] == "trailing_stop"
    assert t["pnl"] == 4.00
    assert t["peak_price"] == 0.45
    assert t["exit_time"] is not None


@pytest.mark.asyncio
async def test_balance_tracking(test_db):
    balance = await db.get_balance()
    assert balance == 5000.0

    await db.log_balance_change(4974.50, trade_id=1, change=-25.50, reason="trade_entry")
    assert await db.get_balance() == 4974.50

    await db.log_balance_change(4979.50, trade_id=1, change=5.00, reason="trade_exit")
    assert await db.get_balance() == 4979.50

    history = await db.get_balance_history()
    assert len(history) == 3
    assert history[0]["reason"] == "initial"
    assert history[-1]["balance"] == 4979.50


@pytest.mark.asyncio
async def test_daily_aggregation(test_db):
    date_str = "2023-11-14"
    ts_base = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc).timestamp()

    for i, pnl_val in enumerate([5.0, -3.0, 2.0]):
        trade = _make_trade(entry_time=ts_base + i * 100)
        tid = await db.log_trade_entry(trade)
        await db.log_trade_exit(
            trade_id=tid,
            exit_price=0.40,
            exit_fee=0.50,
            exit_time=ts_base + i * 100 + 60,
            exit_reason=ExitReason.TRAILING_STOP,
            pnl=pnl_val,
            peak_price=0.42,
            max_favorable=0.07,
        )

    assert await db.get_daily_pnl(date_str) == 4.0
    assert await db.get_daily_trade_count(date_str) == 3


@pytest.mark.asyncio
async def test_trade_stats(test_db):
    ts = 1700000000.0
    pnls = [10.0, -5.0, 3.0, -2.0, 8.0]
    for i, pnl_val in enumerate(pnls):
        trade = _make_trade(entry_time=ts + i * 100)
        tid = await db.log_trade_entry(trade)
        await db.log_trade_exit(
            trade_id=tid,
            exit_price=0.40,
            exit_fee=0.50,
            exit_time=ts + i * 100 + 60,
            exit_reason=ExitReason.TRAILING_STOP,
            pnl=pnl_val,
            peak_price=0.42,
            max_favorable=0.07,
        )

    stats = await db.get_trade_stats()
    assert stats["total_trades"] == 5
    assert stats["wins"] == 3
    assert stats["losses"] == 2
    assert stats["win_rate"] == pytest.approx(0.6)
    assert stats["total_pnl"] == pytest.approx(14.0)
    assert stats["best_trade"] == 10.0
    assert stats["worst_trade"] == -5.0


@pytest.mark.asyncio
async def test_daily_aggregation_no_trades(test_db):
    assert await db.get_daily_pnl("2099-01-01") == 0.0
    assert await db.get_daily_trade_count("2099-01-01") == 0


@pytest.mark.asyncio
async def test_open_trades(test_db):
    ts = 1700000000.0
    t1 = _make_trade(entry_time=ts)
    t2 = _make_trade(entry_time=ts + 100)
    t3 = _make_trade(entry_time=ts + 200)

    tid1 = await db.log_trade_entry(t1)
    await db.log_trade_entry(t2)
    await db.log_trade_entry(t3)

    await db.log_trade_exit(
        trade_id=tid1,
        exit_price=0.40,
        exit_fee=0.50,
        exit_time=ts + 60,
        exit_reason=ExitReason.TRAILING_STOP,
        pnl=3.0,
        peak_price=0.42,
        max_favorable=0.07,
    )

    open_trades = await db.get_open_trades()
    assert len(open_trades) == 2
