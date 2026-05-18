import asyncio
import html as html_lib
import logging
import time
from collections import deque
from datetime import datetime, timezone

from scalper import config
from scalper.models import Direction, ExitReason, Position, Surge, Trade

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self._bot = None
        self._chat_id: str = config.TELEGRAM_CHAT_ID
        self._enabled: bool = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
        self._recent_alerts: deque[dict] = deque(maxlen=100)
        self._send_times: deque[float] = deque(maxlen=20)
        self._rate_limit: int = 20
        self._send_lock: asyncio.Lock = asyncio.Lock()

        if self._enabled:
            from telegram import Bot
            self._bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            logger.info("Telegram notifier enabled (chat_id=%s)", self._chat_id)
        else:
            logger.warning(
                "Telegram notifier disabled — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"
            )

    async def _send(self, text: str, alert_type: str) -> bool:
        alert: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": alert_type,
            "message": text[:200],
            "sent": False,
        }

        if not self._enabled:
            alert["error"] = "disabled"
            self._recent_alerts.appendleft(alert)
            return False

        async with self._send_lock:
            now = time.time()
            if len(self._send_times) >= self._rate_limit:
                oldest = self._send_times[0]
                if now - oldest < 60:
                    wait = 60 - (now - oldest)
                    logger.warning("Telegram rate limit — waiting %.1fs", wait)
                    await asyncio.sleep(wait)

            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode="HTML",
                )
                self._send_times.append(time.time())
                alert["sent"] = True
                self._recent_alerts.appendleft(alert)
                return True
            except Exception as e:
                logger.error("Telegram send failed: %s", e)
                alert["error"] = str(e)
                self._recent_alerts.appendleft(alert)
                return False

    async def send_entry(self, position: Position) -> None:
        direction = "\U0001f7e2 UP" if position.direction == Direction.UP else "\U0001f534 DOWN"
        text = (
            f"<b>\U0001f4c8 ENTRY {direction}</b>\n"
            f"Market: {html_lib.escape(position.market_name[:50])}\n"
            f"Price: {position.entry_price:.2f}\n"
            f"Size: ${position.position_size:.0f} ({position.shares:.0f} shares)\n"
            f"Fee: ${position.entry_fee:.2f}"
        )
        await self._send(text, "entry")

    async def send_exit(self, trade: Trade) -> None:
        direction = "\U0001f7e2 UP" if trade.direction == Direction.UP else "\U0001f534 DOWN"
        pnl = trade.pnl or 0
        pnl_emoji = "✅" if pnl >= 0 else "❌"

        hold_seconds = (trade.exit_time - trade.entry_time) if trade.exit_time else 0.0
        if hold_seconds < 60:
            hold_str = f"{hold_seconds:.0f}s"
        elif hold_seconds < 3600:
            hold_str = f"{hold_seconds / 60:.1f}m"
        else:
            hold_str = f"{hold_seconds / 3600:.1f}h"

        reason_map = {
            ExitReason.TRAILING_STOP: "Trailing Stop",
            ExitReason.TAKE_PROFIT: "Take Profit (90c)",
            ExitReason.DISCONNECT: "Disconnect",
            ExitReason.DAILY_LOSS: "Daily Loss Limit",
            ExitReason.MANUAL: "Manual",
        }
        reason = reason_map.get(trade.exit_reason, str(trade.exit_reason))

        text = (
            f"<b>{pnl_emoji} EXIT {direction}</b>\n"
            f"Market: {html_lib.escape(trade.market_name[:50])}\n"
            f"Entry: {trade.entry_price:.2f} → Exit: {trade.exit_price:.2f}\n"
            f"P&L: <b>{'+' if pnl >= 0 else '-'}${abs(pnl):.2f}</b>\n"
            f"Hold: {hold_str} | Reason: {reason}"
        )
        await self._send(text, "exit")

    async def send_surge(self, surge: Surge, traded: bool) -> None:
        direction = "⬆️" if surge.direction == Direction.UP else "⬇️"
        action = "TRADED" if traded else "skipped"
        text = (
            f"{direction} <b>Surge {surge.direction.value.upper()}</b> ({action})\n"
            f"Market: {html_lib.escape(surge.market_name[:50])}\n"
            f"Magnitude: {surge.magnitude * 100:+.1f}c in {surge.window_seconds:.0f}s\n"
            f"Price: {surge.price_at_detection:.2f}"
        )
        await self._send(text, "surge")

    async def send_daily_summary(self, stats: dict) -> None:
        balance = stats.get("balance", 0)
        total_pnl = stats.get("total_pnl", 0)
        today_pnl = stats.get("today_pnl", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total_trades = stats.get("total_trades", 0)
        today_trades = stats.get("today_trades", 0)
        win_rate = stats.get("win_rate", 0)

        text = (
            f"<b>\U0001f4ca Daily Summary</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Balance: ${balance:,.2f}\n"
            f"Today P&L: {'+' if today_pnl >= 0 else '-'}${abs(today_pnl):.2f} ({today_trades} trades)\n"
            f"All-time P&L: {'+' if total_pnl >= 0 else '-'}${abs(total_pnl):.2f}\n"
            f"Win Rate: {win_rate * 100:.1f}% ({wins}W / {losses}L)\n"
            f"Total Trades: {total_trades}"
        )
        await self._send(text, "daily_summary")

    async def send_error(self, message: str) -> None:
        text = f"<b>⚠️ ERROR</b>\n{message[:500]}"
        await self._send(text, "error")

    async def send_status(self, status: dict) -> None:
        balance = status.get("balance", 0)
        open_pos = status.get("open_positions", 0)
        uptime = status.get("uptime_seconds", 0)

        if uptime < 3600:
            uptime_str = f"{uptime / 60:.0f}m"
        else:
            uptime_str = f"{uptime / 3600:.1f}h"

        text = (
            f"<b>\U0001f4e1 Status Update</b>\n"
            f"Balance: ${balance:,.2f}\n"
            f"Open Positions: {open_pos}\n"
            f"Uptime: {uptime_str}"
        )
        await self._send(text, "status")

    async def send_test(self) -> bool:
        text = (
            f"<b>\U0001f9ea Test Alert</b>\n"
            f"Polymarket Scalper is connected.\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}"
        )
        return await self._send(text, "test")

    def get_recent_alerts(self) -> list[dict]:
        return list(self._recent_alerts)

    def is_enabled(self) -> bool:
        return self._enabled
