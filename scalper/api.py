import time
from dataclasses import asdict

from aiohttp import web

from scalper import config, db


_start_time: float = 0.0
_markets: list[dict] = []
_ws_manager = None
_detector = None
_engine = None
_notifier = None


def set_markets(markets) -> None:
    global _markets
    _markets = [asdict(m) for m in markets]


def set_ws_manager(manager) -> None:
    global _ws_manager
    _ws_manager = manager


def set_detector(detector) -> None:
    global _detector
    _detector = detector


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def set_notifier(notifier) -> None:
    global _notifier
    _notifier = notifier


def _serialize_surge(row: dict) -> dict:
    out = dict(row)
    out["magnitude"] = out.pop("surge_magnitude")
    out["traded"] = bool(out["traded"])
    return out


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@web.middleware
async def auth_middleware(request, handler):
    if not config.API_AUTH_TOKEN:
        return await handler(request)
    if request.path == "/api/health":
        return await handler(request)
    if request.method == "OPTIONS":
        return await handler(request)

    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {config.API_AUTH_TOKEN}":
        raise web.HTTPUnauthorized(text="Invalid or missing auth token")

    return await handler(request)


async def health_handler(request):
    return web.json_response({
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "version": "0.1.0",
    })


async def balance_handler(request):
    balance = await db.get_balance()
    history = await db.get_balance_history()
    return web.json_response({
        "balance": balance,
        "starting_balance": config.STARTING_BALANCE,
        "change": round(balance - config.STARTING_BALANCE, 2),
        "history": history,
    })


def _parse_pagination(request) -> tuple[int, int]:
    try:
        limit = int(request.query.get("limit", "100"))
    except ValueError:
        raise web.HTTPBadRequest(text="limit must be an integer")
    try:
        offset = int(request.query.get("offset", "0"))
    except ValueError:
        raise web.HTTPBadRequest(text="offset must be an integer")
    limit = max(0, min(limit, 500))
    offset = max(0, offset)
    return limit, offset


async def trades_handler(request):
    limit, offset = _parse_pagination(request)
    trades = await db.get_all_trades(limit, offset)
    return web.json_response(trades)


async def open_trades_handler(request):
    trades = await db.get_open_trades()
    return web.json_response(trades)


async def surges_handler(request):
    limit, offset = _parse_pagination(request)
    surges = await db.get_all_surges(limit, offset)
    return web.json_response([_serialize_surge(s) for s in surges])


async def stats_handler(request):
    stats = await db.get_trade_stats()
    return web.json_response(stats)


async def markets_handler(request):
    markets = _markets
    search = request.query.get("search", "").lower()
    category = request.query.get("category", "")

    filtered = markets
    if search:
        filtered = [m for m in filtered if search in m["name"].lower()]
    if category:
        filtered = [m for m in filtered if m["category"].lower() == category.lower()]

    return web.json_response(filtered)


async def markets_stats_handler(request):
    markets = _markets
    total = len(markets)
    total_volume = sum(m["volume_24h"] for m in markets)

    categories: dict[str, int] = {}
    for m in markets:
        cat = m["category"] or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1

    return web.json_response({
        "total_markets": total,
        "total_volume": round(total_volume, 2),
        "total_tokens": total * 2,
        "categories": categories,
    })


async def ws_status_handler(request):
    if _ws_manager is None:
        return web.json_response({
            "state": "disconnected",
            "uptime_seconds": 0,
            "reconnect_count": 0,
            "messages_per_sec": 0,
            "subscribed_tokens": 0,
            "last_message_at": None,
            "total_messages": 0,
            "events_by_type": {},
        })
    return web.json_response(_ws_manager.get_status())


async def detector_stats_handler(request):
    if _detector is None:
        return web.json_response({
            "surges_up": 0,
            "surges_down": 0,
            "active_windows": 0,
            "cooldowns_active": 0,
        })
    return web.json_response(_detector.get_stats())


async def surges_live_handler(request):
    if _detector is None:
        return web.json_response([])
    return web.json_response(_detector.get_recent_surges())


async def positions_handler(request):
    if _engine is None:
        return web.json_response([])
    return web.json_response(_engine.get_open_positions())


async def positions_history_handler(request):
    limit, offset = _parse_pagination(request)
    closed = await db.get_closed_trades(limit, offset)
    return web.json_response(closed)


async def engine_status_handler(request):
    if _engine is None:
        return web.json_response({
            "balance": config.STARTING_BALANCE,
            "starting_balance": config.STARTING_BALANCE,
            "open_positions": 0,
            "daily_pnl": 0,
            "daily_trades": 0,
            "paused": False,
            "uptime_seconds": 0,
        })
    return web.json_response(_engine.get_status())


async def alerts_handler(request):
    if _notifier is None:
        return web.json_response([])
    return web.json_response(_notifier.get_recent_alerts())


async def alerts_test_handler(request):
    if _notifier is None:
        return web.json_response(
            {"success": False, "error": "Notifier not initialized"}, status=503
        )
    success = await _notifier.send_test()
    return web.json_response({"success": success, "enabled": _notifier.is_enabled()})


async def alerts_status_handler(request):
    if _notifier is None:
        return web.json_response({"enabled": False, "configured": False, "chat_id": ""})
    return web.json_response({
        "enabled": _notifier.is_enabled(),
        "configured": bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID),
        "chat_id": config.TELEGRAM_CHAT_ID[:4] + "..." if config.TELEGRAM_CHAT_ID else "",
    })


async def backtest_stats_handler(request):
    from scalper.backtest import compute_stats

    stats = await compute_stats(use_existing_db=True)
    return web.json_response(stats)


async def backtest_simulate_handler(request):
    from scalper.backtest import simulate_params

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON body")

    threshold = body.get("threshold", config.SURGE_THRESHOLD)
    trailing_stop = body.get("trailing_stop", config.TRAILING_STOP_PCT)
    take_profit = body.get("take_profit", config.TAKE_PROFIT)

    try:
        threshold = float(threshold)
        trailing_stop = float(trailing_stop)
        take_profit = float(take_profit)
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="Parameters must be numbers")

    if not (0 < threshold <= 1.0):
        raise web.HTTPBadRequest(text="threshold must be between 0 and 1")
    if not (0 < trailing_stop <= 1.0):
        raise web.HTTPBadRequest(text="trailing_stop must be between 0 and 1")
    if not (0 < take_profit <= 1.0):
        raise web.HTTPBadRequest(text="take_profit must be between 0 and 1")

    result = await simulate_params(
        threshold=threshold,
        trailing_stop=trailing_stop,
        take_profit=take_profit,
        use_existing_db=True,
    )
    return web.json_response(result)


async def backtest_export_trades_handler(request):
    trades = await db.get_all_trades(limit=10000)
    return web.json_response(trades)


async def backtest_export_surges_handler(request):
    surges = await db.get_all_surges(limit=50000)
    return web.json_response([_serialize_surge(s) for s in surges])


async def create_api_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware, auth_middleware])
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/balance", balance_handler)
    app.router.add_get("/api/trades", trades_handler)
    app.router.add_get("/api/trades/open", open_trades_handler)
    app.router.add_get("/api/surges", surges_handler)
    app.router.add_get("/api/stats", stats_handler)
    app.router.add_get("/api/markets", markets_handler)
    app.router.add_get("/api/markets/stats", markets_stats_handler)
    app.router.add_get("/api/ws/status", ws_status_handler)
    app.router.add_get("/api/detector/stats", detector_stats_handler)
    app.router.add_get("/api/surges/live", surges_live_handler)
    app.router.add_get("/api/positions", positions_handler)
    app.router.add_get("/api/positions/history", positions_history_handler)
    app.router.add_get("/api/engine/status", engine_status_handler)
    app.router.add_get("/api/alerts", alerts_handler)
    app.router.add_post("/api/alerts/test", alerts_test_handler)
    app.router.add_get("/api/alerts/status", alerts_status_handler)
    app.router.add_get("/api/backtest/stats", backtest_stats_handler)
    app.router.add_post("/api/backtest/simulate", backtest_simulate_handler)
    app.router.add_get("/api/backtest/export/trades", backtest_export_trades_handler)
    app.router.add_get("/api/backtest/export/surges", backtest_export_surges_handler)
    return app


async def start_api(app: web.Application) -> web.AppRunner:
    global _start_time
    _start_time = time.time()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.API_PORT)
    await site.start()
    return runner
