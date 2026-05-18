import aiosqlite
from datetime import datetime, timezone
from typing import Optional

from scalper import config
from scalper.models import Surge, Trade, ExitReason

_db: Optional[aiosqlite.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS surges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    market_name TEXT,
    direction TEXT NOT NULL,
    surge_magnitude REAL NOT NULL,
    window_seconds REAL NOT NULL,
    price_at_detection REAL NOT NULL,
    traded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    surge_id INTEGER REFERENCES surges(id),
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    market_name TEXT,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_fee REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_price REAL,
    exit_fee REAL,
    exit_time TEXT,
    exit_reason TEXT,
    shares REAL NOT NULL,
    position_size REAL NOT NULL,
    pnl REAL,
    peak_price REAL,
    max_favorable_excursion REAL
);

CREATE TABLE IF NOT EXISTS balance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    balance REAL NOT NULL,
    trade_id INTEGER REFERENCES trades(id),
    change REAL NOT NULL,
    reason TEXT
);
"""


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    return dict(row)


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _db


async def init_db(path: str = None) -> aiosqlite.Connection:
    global _db
    if path is None:
        path = config.DB_PATH
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(_SCHEMA)
    await _db.commit()

    cursor = await _db.execute("SELECT COUNT(*) FROM balance_log")
    count = (await cursor.fetchone())[0]
    if count == 0:
        await _db.execute(
            "INSERT INTO balance_log (timestamp, balance, trade_id, change, reason) VALUES (?, ?, NULL, ?, 'initial')",
            (_now_iso(), config.STARTING_BALANCE, config.STARTING_BALANCE),
        )
        await _db.commit()

    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def log_surge(surge: Surge) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO surges (timestamp, market_id, token_id, market_name, direction, surge_magnitude, window_seconds, price_at_detection, traded)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (
            _ts_to_iso(surge.timestamp),
            surge.market_id,
            surge.token_id,
            surge.market_name,
            surge.direction.value,
            surge.magnitude,
            surge.window_seconds,
            surge.price_at_detection,
        ),
    )
    await db.commit()
    return cursor.lastrowid


async def mark_surge_traded(surge_id: int):
    db = await get_db()
    await db.execute("UPDATE surges SET traded = 1 WHERE id = ?", (surge_id,))
    await db.commit()


async def log_trade_entry(trade: Trade) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO trades (surge_id, market_id, token_id, market_name, direction, entry_price, entry_fee, entry_time, shares, position_size)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trade.surge_id,
            trade.market_id,
            trade.token_id,
            trade.market_name,
            trade.direction.value,
            trade.entry_price,
            trade.entry_fee,
            _ts_to_iso(trade.entry_time),
            trade.shares,
            trade.position_size,
        ),
    )
    await db.commit()
    if trade.surge_id is not None:
        await mark_surge_traded(trade.surge_id)
    return cursor.lastrowid


async def log_trade_exit(
    trade_id: int,
    exit_price: float,
    exit_fee: float,
    exit_time: float,
    exit_reason: ExitReason,
    pnl: float,
    peak_price: float,
    max_favorable: float,
):
    db = await get_db()
    await db.execute(
        """UPDATE trades SET exit_price = ?, exit_fee = ?, exit_time = ?, exit_reason = ?, pnl = ?, peak_price = ?, max_favorable_excursion = ?
           WHERE id = ?""",
        (
            exit_price,
            exit_fee,
            _ts_to_iso(exit_time),
            exit_reason.value,
            pnl,
            peak_price,
            max_favorable,
            trade_id,
        ),
    )
    await db.commit()


async def log_balance_change(balance: float, trade_id: Optional[int], change: float, reason: str):
    db = await get_db()
    await db.execute(
        "INSERT INTO balance_log (timestamp, balance, trade_id, change, reason) VALUES (?, ?, ?, ?, ?)",
        (_now_iso(), balance, trade_id, change, reason),
    )
    await db.commit()


async def get_balance() -> float:
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM balance_log ORDER BY id DESC LIMIT 1")
    row = await cursor.fetchone()
    return row[0] if row else config.STARTING_BALANCE


async def get_balance_history(limit: int = 500) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM balance_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in reversed(rows)]


async def get_daily_pnl(date: str) -> float:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE exit_time IS NOT NULL AND DATE(exit_time) = ?",
        (date,),
    )
    row = await cursor.fetchone()
    return row[0]


async def get_daily_trade_count(date: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM trades WHERE DATE(entry_time) = ?",
        (date,),
    )
    row = await cursor.fetchone()
    return row[0]


async def get_open_trades() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM trades WHERE exit_time IS NULL ORDER BY entry_time DESC")
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in rows]


async def get_all_trades(limit: int = 100, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in rows]


async def get_closed_trades(limit: int = 100, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM trades WHERE exit_time IS NOT NULL ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in rows]


async def get_all_surges(limit: int = 100, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM surges ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in rows]


async def get_trade_stats() -> dict:
    db = await get_db()
    cursor = await db.execute(
        """SELECT
            COUNT(*) as total_trades,
            COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
            COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losses,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COALESCE(AVG(pnl), 0) as avg_pnl,
            COALESCE(MAX(pnl), 0) as best_trade,
            COALESCE(MIN(pnl), 0) as worst_trade
        FROM trades WHERE exit_time IS NOT NULL"""
    )
    row = await cursor.fetchone()
    total = row["total_trades"]
    wins = row["wins"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_pnl = await get_daily_pnl(today)
    today_trades = await get_daily_trade_count(today)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": row["losses"],
        "win_rate": wins / total if total > 0 else 0,
        "total_pnl": row["total_pnl"],
        "avg_pnl": row["avg_pnl"],
        "best_trade": row["best_trade"],
        "worst_trade": row["worst_trade"],
        "today_pnl": today_pnl,
        "today_trades": today_trades,
    }
