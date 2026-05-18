import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, patch

import pytest

from scalper.models import Direction, ExitReason, Position, Surge, Trade


def _make_notifier(enabled=True, bot=None):
    """Create a TelegramNotifier with patched __init__ for testing."""
    from scalper.telegram import TelegramNotifier
    with patch.object(TelegramNotifier, "__init__", lambda self: None):
        n = TelegramNotifier()
    n._bot = bot or (AsyncMock() if enabled else None)
    n._chat_id = "123" if enabled else ""
    n._enabled = enabled
    n._recent_alerts = deque(maxlen=100)
    n._send_times = deque(maxlen=20)
    n._rate_limit = 20
    n._send_lock = asyncio.Lock()
    return n


def _make_position(**overrides):
    defaults = dict(
        id=1,
        market_id="cond_1",
        token_id="tok_yes",
        market_name="Test Market",
        direction=Direction.UP,
        entry_price=0.31,
        entry_fee=0.50,
        entry_time=time.time(),
        shares=80.0,
        position_size=25.0,
        trailing_peak=0.31,
        max_favorable_excursion=0.0,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _make_trade(**overrides):
    now = time.time()
    defaults = dict(
        id=1,
        market_id="cond_1",
        token_id="tok_yes",
        market_name="Test Market",
        direction=Direction.UP,
        entry_price=0.30,
        entry_fee=0.50,
        entry_time=now - 45,
        exit_price=0.38,
        exit_fee=0.50,
        exit_time=now,
        exit_reason=ExitReason.TRAILING_STOP,
        shares=80.0,
        position_size=25.0,
        pnl=5.40,
        peak_price=0.40,
        max_favorable_excursion=0.10,
    )
    defaults.update(overrides)
    return Trade(**defaults)


def _make_surge(**overrides):
    defaults = dict(
        market_id="cond_1",
        token_id="tok_yes",
        market_name="Test Market",
        direction=Direction.UP,
        magnitude=0.12,
        window_seconds=35.0,
        price_at_detection=0.30,
        timestamp=time.time(),
    )
    defaults.update(overrides)
    return Surge(**defaults)


@pytest.mark.asyncio
async def test_disabled_mode_returns_false():
    with patch("scalper.telegram.config") as mock_config:
        mock_config.TELEGRAM_BOT_TOKEN = ""
        mock_config.TELEGRAM_CHAT_ID = ""
        from scalper.telegram import TelegramNotifier
        n = TelegramNotifier()

    assert n.is_enabled() is False
    assert n._bot is None

    result = await n.send_test()
    assert result is False
    alerts = n.get_recent_alerts()
    assert len(alerts) == 1
    assert alerts[0]["sent"] is False
    assert alerts[0]["error"] == "disabled"
    assert alerts[0]["type"] == "test"


@pytest.mark.asyncio
async def test_send_entry_formats_message():
    n = _make_notifier()

    pos = _make_position(direction=Direction.UP, entry_price=0.31, shares=80, position_size=25, entry_fee=0.50)
    await n.send_entry(pos)

    n._bot.send_message.assert_called_once()
    call_kwargs = n._bot.send_message.call_args[1]
    assert "ENTRY" in call_kwargs["text"]
    assert "0.31" in call_kwargs["text"]
    assert call_kwargs["parse_mode"] == "HTML"

    alerts = n.get_recent_alerts()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "entry"
    assert alerts[0]["sent"] is True


@pytest.mark.asyncio
async def test_send_exit_includes_pnl_and_reason():
    n = _make_notifier()

    trade = _make_trade(pnl=5.40, exit_reason=ExitReason.TRAILING_STOP)
    await n.send_exit(trade)

    call_kwargs = n._bot.send_message.call_args[1]
    assert "+$5.40" in call_kwargs["text"]
    assert "Trailing Stop" in call_kwargs["text"]
    assert "EXIT" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_send_exit_negative_pnl():
    n = _make_notifier()

    trade = _make_trade(pnl=-2.30, exit_reason=ExitReason.DAILY_LOSS)
    await n.send_exit(trade)

    call_kwargs = n._bot.send_message.call_args[1]
    assert "-$2.30" in call_kwargs["text"]
    assert "Daily Loss Limit" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_send_surge_traded_and_skipped():
    n = _make_notifier()

    surge = _make_surge(direction=Direction.DOWN, magnitude=0.15)

    await n.send_surge(surge, traded=True)
    call1 = n._bot.send_message.call_args[1]
    assert "TRADED" in call1["text"]
    assert "DOWN" in call1["text"]

    await n.send_surge(surge, traded=False)
    call2 = n._bot.send_message.call_args[1]
    assert "skipped" in call2["text"]


@pytest.mark.asyncio
async def test_send_failure_logs_error():
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("connection timeout")
    n = _make_notifier(bot=bot)

    result = await n.send_test()
    assert result is False
    alerts = n.get_recent_alerts()
    assert alerts[0]["sent"] is False
    assert "connection timeout" in alerts[0]["error"]


@pytest.mark.asyncio
async def test_ring_buffer_maxlen():
    n = _make_notifier(enabled=False)
    n._recent_alerts = deque(maxlen=5)

    for i in range(8):
        await n._send(f"msg {i}", "test")

    alerts = n.get_recent_alerts()
    assert len(alerts) == 5
    assert "msg 7" in alerts[0]["message"]
    assert "msg 3" in alerts[4]["message"]


@pytest.mark.asyncio
async def test_rate_limit_triggers_sleep():
    n = _make_notifier()

    now = time.time()
    for _ in range(20):
        n._send_times.append(now - 10)

    with patch("scalper.telegram.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await n._send("test", "test")
        mock_sleep.assert_called_once()
        wait_time = mock_sleep.call_args[0][0]
        assert 40 < wait_time < 60


@pytest.mark.asyncio
async def test_daily_summary_formats():
    n = _make_notifier()

    stats = {
        "balance": 5120.50,
        "total_pnl": 120.50,
        "today_pnl": 35.20,
        "wins": 8,
        "losses": 3,
        "total_trades": 11,
        "today_trades": 4,
        "win_rate": 0.727,
    }
    await n.send_daily_summary(stats)

    call_kwargs = n._bot.send_message.call_args[1]
    assert "Daily Summary" in call_kwargs["text"]
    assert "$5,120.50" in call_kwargs["text"]
    assert "+$35.20" in call_kwargs["text"]
    assert "72.7%" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_is_enabled():
    n = _make_notifier(enabled=True)
    assert n.is_enabled() is True

    n2 = _make_notifier(enabled=False)
    assert n2.is_enabled() is False
