import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from scalper.websocket import (
    BestBidAskEvent,
    BookSnapshotEvent,
    LastTradePriceEvent,
    WebSocketManager,
    WsState,
)


def test_parse_best_bid_ask():
    mgr = WebSocketManager()
    raw = {
        "event_type": "best_bid_ask",
        "market": "0xabc",
        "asset_id": "token123",
        "best_bid": "0.73",
        "best_ask": "0.77",
        "spread": "0.04",
        "timestamp": "1766789469958",
    }
    event = mgr._parse_event(raw)
    assert isinstance(event, BestBidAskEvent)
    assert event.asset_id == "token123"
    assert event.market_id == "0xabc"
    assert event.best_bid == 0.73
    assert event.best_ask == 0.77
    assert event.spread == 0.04
    assert event.timestamp == pytest.approx(1766789469.958, abs=0.001)


def test_parse_last_trade_price():
    mgr = WebSocketManager()
    raw = {
        "event_type": "last_trade_price",
        "market": "0xdef",
        "asset_id": "token456",
        "price": "0.456",
        "side": "BUY",
        "size": "219.217767",
        "fee_rate_bps": "0",
        "timestamp": "1750428146322",
    }
    event = mgr._parse_event(raw)
    assert isinstance(event, LastTradePriceEvent)
    assert event.price == 0.456
    assert event.side == "BUY"
    assert event.size == pytest.approx(219.217767)
    assert event.timestamp == pytest.approx(1750428146.322, abs=0.001)


def test_parse_book_snapshot():
    mgr = WebSocketManager()
    raw = {
        "event_type": "book",
        "market": "0xabc",
        "asset_id": "token789",
        "bids": [{"price": "0.30", "size": "100"}, {"price": "0.29", "size": "200"}],
        "asks": [{"price": "0.35", "size": "50"}, {"price": "0.36", "size": "75"}],
        "timestamp": "1700000000000",
    }
    event = mgr._parse_event(raw)
    assert isinstance(event, BookSnapshotEvent)
    assert event.best_bid == 0.30
    assert event.best_ask == 0.35


def test_parse_book_empty_orderbook():
    mgr = WebSocketManager()
    raw = {
        "event_type": "book",
        "market": "0xabc",
        "asset_id": "token789",
        "bids": [],
        "asks": [],
        "timestamp": "1700000000000",
    }
    event = mgr._parse_event(raw)
    assert isinstance(event, BookSnapshotEvent)
    assert event.best_bid == 0.0
    assert event.best_ask == 1.0


def test_parse_price_change_ignored():
    mgr = WebSocketManager()
    raw = {
        "event_type": "price_change",
        "market": "0xabc",
        "price_changes": [{"asset_id": "tok", "price": "0.31", "size": "200", "side": "BUY"}],
    }
    event = mgr._parse_event(raw)
    assert event is None


def test_parse_malformed_event():
    mgr = WebSocketManager()
    raw = {"event_type": "best_bid_ask", "asset_id": "tok"}
    event = mgr._parse_event(raw)
    assert event is None


async def test_subscribe_tracks_tokens():
    mgr = WebSocketManager()
    mgr._ws = AsyncMock()
    await mgr.subscribe(["tok_a", "tok_b", "tok_c"])
    assert mgr._subscribed_tokens == {"tok_a", "tok_b", "tok_c"}
    mgr._ws.send.assert_called_once()
    sent = json.loads(mgr._ws.send.call_args[0][0])
    assert sent["type"] == "market"
    assert sent["custom_feature_enabled"] is True
    assert set(sent["assets_ids"]) == {"tok_a", "tok_b", "tok_c"}


async def test_add_tokens():
    mgr = WebSocketManager()
    mgr._ws = AsyncMock()
    mgr._subscribed_tokens = {"tok_a"}
    await mgr.add_tokens(["tok_b", "tok_c"])
    assert mgr._subscribed_tokens == {"tok_a", "tok_b", "tok_c"}
    sent = json.loads(mgr._ws.send.call_args[0][0])
    assert sent["operation"] == "subscribe"


async def test_remove_tokens():
    mgr = WebSocketManager()
    mgr._ws = AsyncMock()
    mgr._subscribed_tokens = {"tok_a", "tok_b", "tok_c"}
    await mgr.remove_tokens(["tok_b"])
    assert mgr._subscribed_tokens == {"tok_a", "tok_c"}
    sent = json.loads(mgr._ws.send.call_args[0][0])
    assert sent["operation"] == "unsubscribe"


def test_get_status():
    mgr = WebSocketManager()
    mgr.state = WsState.CONNECTED
    mgr._subscribed_tokens = {"a", "b", "c"}
    mgr._reconnect_count = 2
    mgr._total_messages = 500
    status = mgr.get_status()
    assert status["state"] == "connected"
    assert status["subscribed_tokens"] == 3
    assert status["reconnect_count"] == 2
    assert status["total_messages"] == 500


@pytest.mark.integration
async def test_websocket_live():
    from scalper.markets import fetch_markets, get_all_token_ids

    markets = await fetch_markets()
    assert len(markets) > 0
    tokens = get_all_token_ids(markets[:2])

    mgr = WebSocketManager()
    await mgr.connect()
    await mgr.subscribe(tokens)

    events = []

    async def collect(event):
        events.append(event)

    async def timeout_listen():
        listen_task = asyncio.create_task(mgr.listen(collect))
        await asyncio.sleep(10)
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

    await timeout_listen()
    await mgr.close()

    print(f"\nReceived {len(events)} events in 10s")
    for e in events[:5]:
        print(f"  {type(e).__name__}: {e}")

    assert len(events) > 0
    assert mgr.get_status()["total_messages"] > 0
