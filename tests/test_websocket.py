import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from scalper.websocket import (
    BestBidAskEvent,
    BookSnapshotEvent,
    LastTradePriceEvent,
    WebSocketManager,
    WsState,
    _WebSocketConnection,
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


async def test_connection_subscribe_tracks_tokens():
    conn = _WebSocketConnection(0)
    conn._ws = AsyncMock()
    conn.state = WsState.CONNECTED
    await conn.subscribe(["tok_a", "tok_b", "tok_c"])
    assert conn._tokens == {"tok_a", "tok_b", "tok_c"}
    conn._ws.send.assert_called_once()
    sent = json.loads(conn._ws.send.call_args[0][0])
    assert sent["type"] == "market"
    assert sent["custom_feature_enabled"] is True
    assert set(sent["assets_ids"]) == {"tok_a", "tok_b", "tok_c"}


async def test_connection_add_tokens():
    conn = _WebSocketConnection(0)
    conn._ws = AsyncMock()
    conn.state = WsState.CONNECTED
    conn._tokens = {"tok_a"}
    await conn.add_tokens(["tok_b", "tok_c"])
    assert conn._tokens == {"tok_a", "tok_b", "tok_c"}
    sent = json.loads(conn._ws.send.call_args[0][0])
    assert sent["operation"] == "subscribe"


async def test_connection_add_tokens_while_disconnected():
    conn = _WebSocketConnection(0)
    conn.state = WsState.RECONNECTING
    conn._tokens = {"tok_a"}
    await conn.add_tokens(["tok_b"])
    assert conn._tokens == {"tok_a", "tok_b"}


async def test_connection_remove_tokens():
    conn = _WebSocketConnection(0)
    conn._ws = AsyncMock()
    conn.state = WsState.CONNECTED
    conn._tokens = {"tok_a", "tok_b", "tok_c"}
    await conn.remove_tokens(["tok_b"])
    assert conn._tokens == {"tok_a", "tok_c"}
    sent = json.loads(conn._ws.send.call_args[0][0])
    assert sent["operation"] == "unsubscribe"


async def test_manager_subscribe_distributes_tokens():
    mgr = WebSocketManager()
    tokens = [f"tok_{i}" for i in range(450)]
    with patch.object(_WebSocketConnection, "connect", new_callable=AsyncMock):
        with patch.object(_WebSocketConnection, "subscribe", new_callable=AsyncMock) as mock_sub:
            await mgr.subscribe(tokens)
    assert len(mgr._connections) == 3
    total_subscribed = sum(
        len(call.args[0]) for call in mock_sub.call_args_list
    )
    assert total_subscribed == 450
    assert len(mgr._connections[0]._tokens) == 0  # subscribe was mocked
    assert len(mgr._token_to_conn) == 450


async def test_manager_add_tokens_fills_existing_connections():
    mgr = WebSocketManager()
    conn = mgr._create_connection()
    conn._ws = AsyncMock()
    conn.state = WsState.CONNECTED
    conn._tokens = {f"tok_{i}" for i in range(190)}
    for tok in conn._tokens:
        mgr._token_to_conn[tok] = conn
    await mgr.add_tokens(["new_a", "new_b"])
    assert "new_a" in conn._tokens
    assert "new_b" in conn._tokens
    assert len(mgr._connections) == 1


def test_get_status():
    mgr = WebSocketManager()
    conn = mgr._create_connection()
    conn.state = WsState.CONNECTED
    conn._tokens = {"a", "b", "c"}
    conn._reconnect_count = 2
    conn._total_messages = 500
    status = mgr.get_status()
    assert status["state"] == "connected"
    assert status["subscribed_tokens"] == 3
    assert status["reconnect_count"] == 2
    assert status["total_messages"] == 500
    assert status["connections"] == 1
    assert status["tokens_per_connection"] == [3]


def test_state_aggregation():
    mgr = WebSocketManager()
    c1 = mgr._create_connection()
    c2 = mgr._create_connection()
    c1.state = WsState.CONNECTED
    c2.state = WsState.RECONNECTING
    assert mgr.state == WsState.CONNECTED

    c1.state = WsState.DISCONNECTED
    assert mgr.state == WsState.RECONNECTING

    c2.state = WsState.DISCONNECTED
    assert mgr.state == WsState.DISCONNECTED


def test_connection_capacity():
    conn = _WebSocketConnection(0)
    assert conn.capacity == 200
    conn._tokens = {f"tok_{i}" for i in range(150)}
    assert conn.capacity == 50


@pytest.mark.integration
async def test_websocket_live():
    from scalper.markets import fetch_markets, get_all_token_ids

    markets = await fetch_markets()
    assert len(markets) > 0
    tokens = get_all_token_ids(markets[:2])

    mgr = WebSocketManager()
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
