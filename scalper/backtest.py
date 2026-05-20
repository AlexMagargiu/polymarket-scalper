import argparse
import asyncio
import json
import logging
from datetime import datetime

from scalper import config, db

logger = logging.getLogger(__name__)


async def compute_stats(use_existing_db: bool = False) -> dict:
    if not use_existing_db:
        await db.init_db()

    conn = await db.get_db()

    trade_stats = await db.get_trade_stats()

    cursor = await conn.execute(
        "SELECT * FROM trades WHERE exit_time IS NOT NULL ORDER BY entry_time"
    )
    trades = [db.row_to_dict(r) for r in await cursor.fetchall()]

    cursor = await conn.execute("SELECT COUNT(*) FROM surges")
    total_surges = (await cursor.fetchone())[0]

    cursor = await conn.execute("SELECT COUNT(*) FROM surges WHERE traded = 1")
    traded_surges = (await cursor.fetchone())[0]

    balance = await db.get_balance()

    # Max drawdown from balance log
    cursor = await conn.execute("SELECT balance FROM balance_log ORDER BY id")
    balances = [r[0] for r in await cursor.fetchall()]

    peak = config.STARTING_BALANCE
    max_drawdown = 0.0
    for b in balances:
        if b > peak:
            peak = b
        dd = peak - b
        if dd > max_drawdown:
            max_drawdown = dd

    # Profit factor
    gross_profit = sum(t["pnl"] for t in trades if (t["pnl"] or 0) > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if (t["pnl"] or 0) < 0))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    # Average hold duration
    hold_durations = []
    for t in trades:
        if t["entry_time"] and t["exit_time"]:
            entry = datetime.fromisoformat(t["entry_time"]).timestamp()
            exit_ = datetime.fromisoformat(t["exit_time"]).timestamp()
            hold_durations.append(exit_ - entry)
    avg_hold = sum(hold_durations) / len(hold_durations) if hold_durations else 0

    # Wins / losses averages
    wins = [t["pnl"] for t in trades if (t["pnl"] or 0) > 0]
    losses = [t["pnl"] for t in trades if (t["pnl"] or 0) < 0]

    # Trades per day
    trades_per_day: dict[str, int] = {}
    for t in trades:
        day = t["entry_time"][:10] if t["entry_time"] else "unknown"
        trades_per_day[day] = trades_per_day.get(day, 0) + 1

    # P&L by market
    pnl_by_market: dict[str, float] = {}
    for t in trades:
        name = t.get("market_name") or "Unknown"
        pnl_by_market[name] = pnl_by_market.get(name, 0) + (t["pnl"] or 0)
    pnl_by_market = dict(
        sorted(pnl_by_market.items(), key=lambda x: abs(x[1]), reverse=True)[:20]
    )

    # Surge conversion
    conversion_rate = traded_surges / total_surges if total_surges > 0 else 0

    # MFE analysis
    mfe_values = [
        t["max_favorable_excursion"]
        for t in trades
        if t.get("max_favorable_excursion") is not None
    ]
    avg_mfe = sum(mfe_values) / len(mfe_values) if mfe_values else 0

    result = {
        **trade_stats,
        "balance": balance,
        "starting_balance": config.STARTING_BALANCE,
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_hold_seconds": round(avg_hold, 1),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "trades_per_day": trades_per_day,
        "pnl_by_market": pnl_by_market,
        "total_surges": total_surges,
        "traded_surges": traded_surges,
        "surge_conversion_rate": round(conversion_rate, 4),
        "avg_mfe": round(avg_mfe, 4),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }

    if not use_existing_db:
        await db.close_db()

    return result


async def export_trades(use_existing_db: bool = False) -> list[dict]:
    if not use_existing_db:
        await db.init_db()

    trades = await db.get_all_trades(limit=10000, offset=0)

    if not use_existing_db:
        await db.close_db()

    return trades


async def export_surges(use_existing_db: bool = False) -> list[dict]:
    if not use_existing_db:
        await db.init_db()

    surges = await db.get_all_surges(limit=50000, offset=0)

    if not use_existing_db:
        await db.close_db()

    return surges


async def simulate_params(
    threshold: float = config.SURGE_THRESHOLD,
    trailing_stop: float = config.TRAILING_STOP_PCT,
    take_profit: float = config.TAKE_PROFIT,
    use_existing_db: bool = False,
) -> dict:
    if not use_existing_db:
        await db.init_db()

    conn = await db.get_db()

    cursor = await conn.execute(
        """SELECT t.*, s.surge_magnitude
           FROM trades t
           LEFT JOIN surges s ON t.surge_id = s.id
           WHERE t.exit_time IS NOT NULL
           ORDER BY t.entry_time"""
    )
    trades = [db.row_to_dict(r) for r in await cursor.fetchall()]

    if not use_existing_db:
        await db.close_db()

    sim_trades = 0
    sim_pnl = 0.0
    sim_wins = 0
    sim_skipped = 0
    orig_pnl = 0.0
    orig_wins = 0

    for t in trades:
        surge_mag = t.get("surge_magnitude") or 0
        if surge_mag < threshold:
            sim_skipped += 1
            orig_pnl += t["pnl"] or 0
            if (t["pnl"] or 0) > 0:
                orig_wins += 1
            continue
        entry_price = t["entry_price"]
        peak = t.get("peak_price") or entry_price
        shares = t["shares"]
        direction = t["direction"]
        entry_fee = t["entry_fee"]
        orig_trade_pnl = t["pnl"] or 0

        orig_pnl += orig_trade_pnl
        if orig_trade_pnl > 0:
            orig_wins += 1

        if direction == "up":
            favorable = peak - entry_price
            if favorable >= take_profit - entry_price and take_profit > entry_price:
                sim_exit = take_profit
            elif peak - trailing_stop > entry_price:
                sim_exit = peak - trailing_stop
            else:
                sim_exit = t.get("exit_price") or entry_price
            pnl = (sim_exit - entry_price) * shares - entry_fee - (
                shares * sim_exit * config.TAKER_FEE_RATE
            )
        else:
            favorable = entry_price - peak
            if favorable >= entry_price - (1.0 - take_profit) and (1.0 - take_profit) < entry_price:
                sim_exit = 1.0 - take_profit
            elif peak + trailing_stop < entry_price:
                sim_exit = peak + trailing_stop
            else:
                sim_exit = t.get("exit_price") or entry_price
            pnl = (entry_price - sim_exit) * shares - entry_fee - (
                shares * sim_exit * config.TAKER_FEE_RATE
            )

        sim_trades += 1
        sim_pnl += pnl
        if pnl > 0:
            sim_wins += 1

    total = len(trades)

    return {
        "params": {
            "threshold": threshold,
            "trailing_stop": trailing_stop,
            "take_profit": take_profit,
        },
        "original": {
            "total_trades": total,
            "total_pnl": round(orig_pnl, 2),
            "wins": orig_wins,
            "losses": total - orig_wins,
            "win_rate": round(orig_wins / total, 4) if total > 0 else 0,
        },
        "simulated": {
            "total_trades": sim_trades,
            "total_pnl": round(sim_pnl, 2),
            "wins": sim_wins,
            "losses": sim_trades - sim_wins,
            "win_rate": round(sim_wins / sim_trades, 4) if sim_trades > 0 else 0,
            "skipped_by_threshold": sim_skipped,
        },
    }


def cli():
    parser = argparse.ArgumentParser(description="Polymarket Scalper Backtest")
    parser.add_argument("--stats", action="store_true", help="Show trade statistics")
    parser.add_argument(
        "--export", action="store_true", help="Export trades and surges to CSV"
    )
    parser.add_argument(
        "--simulate", action="store_true", help="Run parameter simulation"
    )
    parser.add_argument("--db", default=config.DB_PATH, help="Database path")
    parser.add_argument("--threshold", type=float, default=config.SURGE_THRESHOLD)
    parser.add_argument("--trailing", type=float, default=config.TRAILING_STOP_PCT)
    parser.add_argument("--take-profit", type=float, default=config.TAKE_PROFIT)
    args = parser.parse_args()

    if args.db != config.DB_PATH:
        import scalper.config as cfg
        cfg.DB_PATH = args.db

    if args.stats:
        stats = asyncio.run(compute_stats())
        print(json.dumps(stats, indent=2))
    elif args.export:
        import csv
        import sys

        trades = asyncio.run(export_trades())
        if trades:
            writer = csv.DictWriter(sys.stdout, fieldnames=trades[0].keys())
            writer.writeheader()
            writer.writerows(trades)
        else:
            print("No trades to export")
    elif args.simulate:
        result = asyncio.run(
            simulate_params(args.threshold, args.trailing, args.take_profit)
        )
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
