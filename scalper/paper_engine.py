import logging
import time
from datetime import datetime, timezone
from typing import Optional

from scalper import config, db
from scalper.models import (
    Direction,
    ExitReason,
    Position,
    PositionStatus,
    Surge,
    Trade,
)

logger = logging.getLogger(__name__)


class PaperEngine:
    def __init__(self):
        self._positions: dict[int, Position] = {}
        self._balance: float = config.STARTING_BALANCE
        self._daily_pnl: float = 0.0
        self._daily_trades: int = 0
        self._daily_date: str = ""
        self._paused: bool = False
        self._start_time: float = time.time()
        self._last_prices: dict[str, tuple[float, float]] = {}

    async def init(self):
        self._balance = await db.get_balance()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily_date = today
        self._daily_pnl = await db.get_daily_pnl(today)
        self._daily_trades = await db.get_daily_trade_count(today)
        if self._daily_pnl <= -config.DAILY_LOSS_LIMIT:
            self._paused = True

        open_trades = await db.get_open_trades()
        for row in open_trades:
            pos = Position(
                id=row["id"],
                market_id=row["market_id"],
                token_id=row["token_id"],
                market_name=row["market_name"],
                direction=Direction(row["direction"]),
                entry_price=row["entry_price"],
                entry_fee=row["entry_fee"],
                entry_time=datetime.fromisoformat(row["entry_time"]).timestamp(),
                shares=row["shares"],
                position_size=row["position_size"],
                trailing_peak=row.get("peak_price") or row["entry_price"],
                status=PositionStatus.OPEN,
                surge_id=row.get("surge_id"),
            )
            self._positions[row["id"]] = pos

        logger.info(
            "Engine initialized: balance=$%.2f, %d open positions",
            self._balance,
            len(self._positions),
        )

    async def on_surge(
        self,
        surge: Surge,
        current_bid: float,
        current_ask: float,
    ) -> Optional[Position]:
        self._check_daily_reset()

        if surge.direction == Direction.UP:
            entry_price = current_ask
        else:
            entry_price = current_bid

        rejection = self._validate_entry(surge, entry_price)
        if rejection:
            logger.debug("Entry rejected for %s: %s", surge.market_name[:30], rejection)
            return None

        shares = config.POSITION_SIZE / entry_price
        entry_fee = config.POSITION_SIZE * config.TAKER_FEE_RATE

        surge_id = await db.log_surge(surge)

        trade = Trade(
            surge_id=surge_id,
            market_id=surge.market_id,
            token_id=surge.token_id,
            market_name=surge.market_name,
            direction=surge.direction,
            entry_price=entry_price,
            entry_fee=entry_fee,
            entry_time=surge.timestamp,
            shares=shares,
            position_size=config.POSITION_SIZE,
        )
        trade_id = await db.log_trade_entry(trade)

        cost = config.POSITION_SIZE + entry_fee
        self._balance -= cost
        await db.log_balance_change(self._balance, trade_id, -cost, "trade_entry")

        self._daily_trades += 1

        position = Position(
            id=trade_id,
            market_id=surge.market_id,
            token_id=surge.token_id,
            market_name=surge.market_name,
            direction=surge.direction,
            entry_price=entry_price,
            entry_fee=entry_fee,
            entry_time=surge.timestamp,
            shares=shares,
            position_size=config.POSITION_SIZE,
            trailing_peak=entry_price,
            status=PositionStatus.OPEN,
            surge_id=surge_id,
        )
        self._positions[trade_id] = position

        logger.info(
            "ENTRY %s: %s @ %.2f (%d shares, fee=$%.2f) [balance=$%.2f]",
            surge.direction.value.upper(),
            surge.market_name[:30],
            entry_price,
            int(shares),
            entry_fee,
            self._balance,
        )

        return position

    def _validate_entry(self, surge: Surge, entry_price: float) -> Optional[str]:
        if self._paused:
            return "trading paused (daily loss limit)"

        if self._balance < config.POSITION_SIZE:
            return f"insufficient balance (${self._balance:.2f} < ${config.POSITION_SIZE})"

        if len(self._positions) >= config.MAX_CONCURRENT_POSITIONS:
            return f"max concurrent positions ({config.MAX_CONCURRENT_POSITIONS})"

        market_count = sum(
            1 for p in self._positions.values() if p.market_id == surge.market_id
        )
        if market_count >= config.MAX_POSITIONS_PER_MARKET:
            return f"max positions per market ({config.MAX_POSITIONS_PER_MARKET})"

        if self._daily_trades >= config.MAX_DAILY_TRADES:
            return f"max daily trades ({config.MAX_DAILY_TRADES})"

        if self._daily_pnl <= -config.DAILY_LOSS_LIMIT:
            self._paused = True
            return f"daily loss limit (${config.DAILY_LOSS_LIMIT})"

        if entry_price < config.MIN_ENTRY_PRICE:
            return f"price too low ({entry_price:.2f} < {config.MIN_ENTRY_PRICE})"

        if surge.direction == Direction.UP and entry_price > config.MAX_ENTRY_PRICE_YES:
            return f"YES entry too high ({entry_price:.2f} > {config.MAX_ENTRY_PRICE_YES})"

        if surge.direction == Direction.DOWN and entry_price < config.MIN_ENTRY_PRICE_NO:
            return f"NO entry too low ({entry_price:.2f} < {config.MIN_ENTRY_PRICE_NO})"

        return None

    async def on_price_update(
        self,
        token_id: str,
        best_bid: float,
        best_ask: float,
        timestamp: float,
    ) -> list[Trade]:
        self._check_daily_reset()
        self._last_prices[token_id] = (best_bid, best_ask)
        midpoint = (best_bid + best_ask) / 2

        closed_trades: list[Trade] = []

        positions = [
            (tid, pos)
            for tid, pos in self._positions.items()
            if pos.token_id == token_id
        ]

        for trade_id, pos in positions:
            exit_reason = None
            exit_price = None

            if pos.direction == Direction.UP:
                if midpoint > pos.trailing_peak:
                    pos.trailing_peak = midpoint

                mfe = midpoint - pos.entry_price
                if mfe > pos.max_favorable_excursion:
                    pos.max_favorable_excursion = mfe

                if pos.trailing_peak - midpoint >= config.TRAILING_STOP:
                    exit_reason = ExitReason.TRAILING_STOP
                    exit_price = best_bid

                if midpoint >= config.TAKE_PROFIT:
                    exit_reason = ExitReason.TAKE_PROFIT
                    exit_price = best_bid

            else:
                if pos.trailing_peak == pos.entry_price or midpoint < pos.trailing_peak:
                    pos.trailing_peak = midpoint

                mfe = pos.entry_price - midpoint
                if mfe > pos.max_favorable_excursion:
                    pos.max_favorable_excursion = mfe

                if midpoint - pos.trailing_peak >= config.TRAILING_STOP:
                    exit_reason = ExitReason.TRAILING_STOP
                    exit_price = best_ask

                if midpoint <= (1.0 - config.TAKE_PROFIT):
                    exit_reason = ExitReason.TAKE_PROFIT
                    exit_price = best_ask

            if exit_reason:
                trade = await self._close_position(
                    trade_id, pos, exit_price, exit_reason, timestamp
                )
                if trade:
                    closed_trades.append(trade)

        return closed_trades

    async def _close_position(
        self,
        trade_id: int,
        pos: Position,
        exit_price: float,
        exit_reason: ExitReason,
        timestamp: float,
    ) -> Optional[Trade]:
        exit_fee = pos.shares * exit_price * config.TAKER_FEE_RATE

        if pos.direction == Direction.UP:
            pnl = (exit_price - pos.entry_price) * pos.shares - pos.entry_fee - exit_fee
        else:
            pnl = (pos.entry_price - exit_price) * pos.shares - pos.entry_fee - exit_fee

        pnl = round(pnl, 2)

        await db.log_trade_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_fee=exit_fee,
            exit_time=timestamp,
            exit_reason=exit_reason,
            pnl=pnl,
            peak_price=pos.trailing_peak,
            max_favorable=pos.max_favorable_excursion,
        )

        proceeds = pos.shares * exit_price - exit_fee
        self._balance += proceeds
        await db.log_balance_change(self._balance, trade_id, proceeds, "trade_exit")

        self._daily_pnl += pnl

        if self._daily_pnl <= -config.DAILY_LOSS_LIMIT:
            self._paused = True
            logger.warning(
                "Daily loss limit hit ($%.2f) — trading paused", self._daily_pnl
            )

        del self._positions[trade_id]

        logger.info(
            "EXIT %s (%s): %s @ %.2f → %.2f | P&L: $%.2f [balance=$%.2f]",
            pos.direction.value.upper(),
            exit_reason.value,
            pos.market_name[:30],
            pos.entry_price,
            exit_price,
            pnl,
            self._balance,
        )

        return Trade(
            id=trade_id,
            surge_id=pos.surge_id,
            market_id=pos.market_id,
            token_id=pos.token_id,
            market_name=pos.market_name,
            direction=pos.direction,
            entry_price=pos.entry_price,
            entry_fee=pos.entry_fee,
            entry_time=pos.entry_time,
            exit_price=exit_price,
            exit_fee=exit_fee,
            exit_time=timestamp,
            exit_reason=exit_reason,
            shares=pos.shares,
            position_size=pos.position_size,
            pnl=pnl,
            peak_price=pos.trailing_peak,
            max_favorable_excursion=pos.max_favorable_excursion,
        )

    async def on_disconnect(self) -> list[Trade]:
        if not self._positions:
            return []

        logger.warning("DISCONNECT — closing %d positions", len(self._positions))
        closed: list[Trade] = []
        now = time.time()

        for trade_id, pos in list(self._positions.items()):
            last = self._last_prices.get(pos.token_id)
            if last:
                bid, ask = last
            else:
                bid = ask = pos.entry_price

            if pos.direction == Direction.UP:
                exit_price = bid
            else:
                exit_price = ask

            trade = await self._close_position(
                trade_id, pos, exit_price, ExitReason.DISCONNECT, now
            )
            if trade:
                closed.append(trade)

        return closed

    def _check_daily_reset(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_date:
            self._daily_date = today
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._paused = False

    def get_status(self) -> dict:
        self._check_daily_reset()
        return {
            "balance": round(self._balance, 2),
            "starting_balance": config.STARTING_BALANCE,
            "open_positions": len(self._positions),
            "daily_pnl": round(self._daily_pnl, 2),
            "daily_trades": self._daily_trades,
            "paused": self._paused,
            "uptime_seconds": round(time.time() - self._start_time, 1),
        }

    def get_open_positions(self) -> list[dict]:
        result = []
        for trade_id, pos in self._positions.items():
            last = self._last_prices.get(pos.token_id)
            if last:
                bid, ask = last
                current_price = (bid + ask) / 2
            else:
                current_price = pos.entry_price

            projected_exit_fee = pos.shares * current_price * config.TAKER_FEE_RATE
            if pos.direction == Direction.UP:
                unrealized = (current_price - pos.entry_price) * pos.shares - pos.entry_fee - projected_exit_fee
            else:
                unrealized = (pos.entry_price - current_price) * pos.shares - pos.entry_fee - projected_exit_fee

            result.append(
                {
                    "id": trade_id,
                    "market_id": pos.market_id,
                    "token_id": pos.token_id,
                    "market_name": pos.market_name,
                    "direction": pos.direction.value,
                    "entry_price": pos.entry_price,
                    "entry_fee": pos.entry_fee,
                    "entry_time": datetime.fromtimestamp(
                        pos.entry_time, tz=timezone.utc
                    ).isoformat(),
                    "shares": round(pos.shares, 2),
                    "position_size": pos.position_size,
                    "trailing_peak": round(pos.trailing_peak, 4),
                    "max_favorable_excursion": round(pos.max_favorable_excursion, 4),
                    "current_price": round(current_price, 4),
                    "unrealized_pnl": round(unrealized, 2),
                }
            )
        return result
