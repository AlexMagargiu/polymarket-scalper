import asyncio
import logging
import signal
import time
from datetime import datetime, timedelta, timezone

from scalper import config, db
from scalper.api import (
    create_api_app,
    set_detector,
    set_engine,
    set_markets,
    set_notifier,
    set_ws_manager,
    start_api,
)
from scalper.detector import TrendDetector
from scalper.markets import (
    build_token_to_market_map,
    fetch_markets,
    get_all_token_ids,
    refresh_markets,
)
from scalper.paper_engine import PaperEngine
from scalper.telegram import TelegramNotifier
from scalper.websocket import (
    BestBidAskEvent,
    BookSnapshotEvent,
    LastTradePriceEvent,
    WebSocketManager,
)

logger = logging.getLogger(__name__)


async def main():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
    )

    logger.info("Starting Polymarket Momentum Scalper")

    await db.init_db()

    notifier = TelegramNotifier()
    detector = TrendDetector()
    engine = PaperEngine()
    await engine.init()

    app = await create_api_app()
    api_runner = await start_api(app)
    logger.info("API server started on port %d", config.API_PORT)

    set_notifier(notifier)
    set_detector(detector)
    set_engine(engine)

    markets = await fetch_markets()
    if not markets:
        logger.error("No markets found — exiting")
        await notifier.send_error("No markets found from Gamma API — bot cannot start")
        await api_runner.cleanup()
        await db.close_db()
        return

    set_markets(markets)
    token_map = build_token_to_market_map(markets)
    detector.set_token_map(token_map)
    all_tokens = get_all_token_ids(markets)

    logger.info("Fetched %d markets (%d tokens)", len(markets), len(all_tokens))

    ws = WebSocketManager()
    await ws.subscribe(all_tokens)
    set_ws_manager(ws)

    await notifier.send_status(engine.get_status())

    async def on_event(event):
        try:
            if isinstance(event, BestBidAskEvent):
                trend = detector.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )

                closed_trades = await engine.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )
                for trade in closed_trades:
                    await notifier.send_exit(trade)

                if trend:
                    position = await engine.on_trend(
                        trend, event.best_bid, event.best_ask
                    )
                    if position:
                        await notifier.send_entry(position)

            elif isinstance(event, BookSnapshotEvent):
                detector.on_price_update(
                    event.asset_id, event.best_bid, event.best_ask, event.timestamp
                )

            elif isinstance(event, LastTradePriceEvent):
                detector.on_trade(
                    event.asset_id, event.price, event.side, event.size, event.timestamp
                )

            elif event == "DISCONNECT":
                logger.warning("Prolonged disconnect — closing all positions")
                closed = await engine.on_disconnect()
                for trade in closed:
                    await notifier.send_exit(trade)
                await notifier.send_error(
                    "WebSocket disconnected >30s — all positions closed"
                )

        except Exception:
            logger.exception("Error processing event")

    async def market_refresher_task():
        nonlocal markets, token_map
        while True:
            await asyncio.sleep(config.MARKET_REFRESH_INTERVAL)
            try:
                new_markets, added, removed = await refresh_markets(markets)
                if added or removed:
                    markets = new_markets
                    set_markets(markets)
                    token_map = build_token_to_market_map(markets)
                    detector.set_token_map(token_map)
                    if added:
                        await ws.add_tokens(added)
                    if removed:
                        await ws.remove_tokens(removed)
                    logger.info(
                        "Market refresh: +%d -%d tokens", len(added), len(removed)
                    )
            except Exception:
                logger.exception("Market refresh failed")

    async def status_reporter_task():
        while True:
            await asyncio.sleep(900)
            try:
                await notifier.send_status(engine.get_status())
            except Exception:
                logger.exception("Status report failed")

    async def daily_summary_task():
        while True:
            now = datetime.now(timezone.utc)
            tomorrow = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            await asyncio.sleep((tomorrow - now).total_seconds() + 5)
            try:
                stats = await db.get_trade_stats()
                stats["balance"] = await db.get_balance()
                await notifier.send_daily_summary(stats)
            except Exception:
                logger.exception("Daily summary failed")

    async def stale_pruner_task():
        while True:
            await asyncio.sleep(300)
            try:
                detector.prune_stale_tokens()
            except Exception:
                logger.exception("Stale prune failed")

    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    tasks = [
        asyncio.create_task(ws.listen(on_event), name="ws_listener"),
        asyncio.create_task(market_refresher_task(), name="market_refresher"),
        asyncio.create_task(status_reporter_task(), name="status_reporter"),
        asyncio.create_task(daily_summary_task(), name="daily_summary"),
        asyncio.create_task(stale_pruner_task(), name="stale_pruner"),
    ]

    await shutdown_event.wait()

    logger.info("Shutting down...")

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    closed = await engine.on_disconnect()
    for trade in closed:
        await notifier.send_exit(trade)

    await ws.close()
    await api_runner.cleanup()
    await db.close_db()

    logger.info("Shutdown complete")
