import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import websockets

from scalper import config

logger = logging.getLogger(__name__)


class WsState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class BestBidAskEvent:
    asset_id: str
    market_id: str
    best_bid: float
    best_ask: float
    spread: float
    timestamp: float


@dataclass
class LastTradePriceEvent:
    asset_id: str
    market_id: str
    price: float
    side: str
    size: float
    timestamp: float


@dataclass
class BookSnapshotEvent:
    asset_id: str
    market_id: str
    best_bid: float
    best_ask: float
    timestamp: float


def _parse_event(data: dict) -> Optional[object]:
    event_type = data.get("event_type", "")

    if event_type == "best_bid_ask":
        try:
            return BestBidAskEvent(
                asset_id=data["asset_id"],
                market_id=data["market"],
                best_bid=float(data["best_bid"]),
                best_ask=float(data["best_ask"]),
                spread=float(data.get("spread", "0")),
                timestamp=float(data["timestamp"]) / 1000,
            )
        except (KeyError, ValueError):
            return None

    elif event_type == "last_trade_price":
        try:
            return LastTradePriceEvent(
                asset_id=data["asset_id"],
                market_id=data["market"],
                price=float(data["price"]),
                side=data.get("side", ""),
                size=float(data.get("size", "0")),
                timestamp=float(data["timestamp"]) / 1000,
            )
        except (KeyError, ValueError):
            return None

    elif event_type == "book":
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            best_bid = max((float(b["price"]) for b in bids), default=0.0)
            best_ask = min((float(a["price"]) for a in asks), default=1.0)
            return BookSnapshotEvent(
                asset_id=data["asset_id"],
                market_id=data["market"],
                best_bid=best_bid,
                best_ask=best_ask,
                timestamp=float(data.get("timestamp", "0")) / 1000,
            )
        except (KeyError, ValueError, IndexError):
            return None

    return None


def _chunk_list(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


class _WebSocketConnection:
    """Single WebSocket connection handling a subset of tokens."""

    def __init__(self, conn_id: int):
        self.conn_id = conn_id
        self.state: WsState = WsState.DISCONNECTED
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._tokens: set[str] = set()
        self._reconnect_delay: float = config.RECONNECT_INITIAL_DELAY
        self._connect_time: float = 0.0
        self._reconnect_count: int = 0
        self._total_messages: int = 0
        self._messages_last_sec: int = 0
        self._last_message_time: float = 0.0
        self._last_rate_calc: float = 0.0
        self._events_by_type: dict[str, int] = {}

    @property
    def capacity(self) -> int:
        return config.WS_MAX_TOKENS_PER_CONNECTION - len(self._tokens)

    async def connect(self):
        logger.info("[conn-%d] Connecting to %s", self.conn_id, config.WS_URL)
        self._ws = await websockets.connect(config.WS_URL)
        self.state = WsState.CONNECTED
        self._connect_time = time.time()
        self._reconnect_delay = config.RECONNECT_INITIAL_DELAY
        logger.info("[conn-%d] Connected", self.conn_id)

    async def subscribe(self, token_ids: list[str]):
        if not self._ws:
            raise RuntimeError("Not connected")
        msg = {
            "assets_ids": token_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }
        await self._ws.send(json.dumps(msg))
        self._tokens.update(token_ids)
        logger.info(
            "[conn-%d] Subscribed to %d tokens (total: %d)",
            self.conn_id, len(token_ids), len(self._tokens),
        )

    async def add_tokens(self, token_ids: list[str]):
        if not token_ids:
            return
        self._tokens.update(token_ids)
        if not self._ws or self.state != WsState.CONNECTED:
            logger.debug(
                "[conn-%d] Queued %d tokens for resubscribe on reconnect",
                self.conn_id, len(token_ids),
            )
            return
        msg = {
            "assets_ids": token_ids,
            "operation": "subscribe",
            "custom_feature_enabled": True,
        }
        try:
            await self._ws.send(json.dumps(msg))
            logger.info(
                "[conn-%d] Added %d tokens (total: %d)",
                self.conn_id, len(token_ids), len(self._tokens),
            )
        except Exception:
            logger.debug(
                "[conn-%d] Failed to send add_tokens, will resubscribe on reconnect",
                self.conn_id,
            )

    async def remove_tokens(self, token_ids: list[str]):
        if not token_ids:
            return
        self._tokens.difference_update(token_ids)
        if not self._ws or self.state != WsState.CONNECTED:
            return
        msg = {
            "assets_ids": token_ids,
            "operation": "unsubscribe",
        }
        try:
            await self._ws.send(json.dumps(msg))
        except Exception:
            logger.warning("[conn-%d] Failed to send remove_tokens", self.conn_id)

    async def listen(self, callback: Callable):
        while True:
            try:
                await self._listen_loop(callback)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning("[conn-%d] Disconnected: %s", self.conn_id, e)
                self.state = WsState.RECONNECTING
                await self._handle_reconnect()
            except asyncio.CancelledError:
                logger.info("[conn-%d] Listener cancelled", self.conn_id)
                await self.close()
                return

    async def _listen_loop(self, callback: Callable):
        heartbeat_task = asyncio.create_task(self._heartbeat())
        try:
            async for raw_msg in self._ws:
                if raw_msg == "PONG":
                    continue

                self._total_messages += 1
                self._messages_last_sec += 1
                self._last_message_time = time.time()
                self._update_rate()

                try:
                    data = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, list):
                    for item in data:
                        event = _parse_event(item)
                        if event:
                            self._events_by_type[type(event).__name__] = (
                                self._events_by_type.get(type(event).__name__, 0) + 1
                            )
                            await callback(event)
                else:
                    event = _parse_event(data)
                    if event:
                        self._events_by_type[type(event).__name__] = (
                            self._events_by_type.get(type(event).__name__, 0) + 1
                        )
                        await callback(event)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(10)
            if self._ws:
                try:
                    await self._ws.send("PING")
                except Exception:
                    break

    async def _handle_reconnect(self):
        while True:
            logger.info(
                "[conn-%d] Reconnecting in %.1fs (attempt %d)",
                self.conn_id, self._reconnect_delay, self._reconnect_count + 1,
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * config.RECONNECT_MULTIPLIER,
                config.RECONNECT_MAX_DELAY,
            )
            self._reconnect_count += 1

            try:
                await self.connect()
                if self._tokens:
                    await self.subscribe(list(self._tokens))
                logger.info(
                    "[conn-%d] Reconnected and resubscribed to %d tokens",
                    self.conn_id, len(self._tokens),
                )
                return
            except Exception as e:
                logger.error("[conn-%d] Reconnect failed: %s", self.conn_id, e)

    def _update_rate(self):
        now = time.time()
        if now - self._last_rate_calc >= 1.0:
            self._messages_last_sec = 0
            self._last_rate_calc = now

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self.state = WsState.DISCONNECTED


class WebSocketManager:
    """Manages a pool of WebSocket connections, distributing tokens across them."""

    def __init__(self):
        self._connections: list[_WebSocketConnection] = []
        self._token_to_conn: dict[str, _WebSocketConnection] = {}
        self._callback: Optional[Callable] = None
        self._listener_tasks: list[asyncio.Task] = []
        self._listen_event: Optional[asyncio.Event] = None
        self._next_conn_id: int = 0

    @property
    def state(self) -> WsState:
        if any(c.state == WsState.CONNECTED for c in self._connections):
            return WsState.CONNECTED
        if any(c.state == WsState.RECONNECTING for c in self._connections):
            return WsState.RECONNECTING
        return WsState.DISCONNECTED

    async def connect(self):
        pass

    async def subscribe(self, token_ids: list[str]):
        chunks = _chunk_list(token_ids, config.WS_MAX_TOKENS_PER_CONNECTION)
        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(1)
            conn = self._create_connection()
            await conn.connect()
            await conn.subscribe(chunk)
            for tok in chunk:
                self._token_to_conn[tok] = conn
        logger.info(
            "Subscribed to %d tokens across %d connections",
            len(token_ids), len(self._connections),
        )

    async def add_tokens(self, token_ids: list[str]):
        if not token_ids:
            return
        remaining = list(token_ids)

        for conn in self._connections:
            if not remaining:
                break
            if conn.capacity > 0:
                batch = remaining[: conn.capacity]
                remaining = remaining[conn.capacity :]
                await conn.add_tokens(batch)
                for tok in batch:
                    self._token_to_conn[tok] = conn

        while remaining:
            batch = remaining[: config.WS_MAX_TOKENS_PER_CONNECTION]
            remaining = remaining[config.WS_MAX_TOKENS_PER_CONNECTION :]
            conn = self._create_connection()
            await conn.connect()
            await conn.subscribe(batch)
            for tok in batch:
                self._token_to_conn[tok] = conn
            if self._callback:
                task = asyncio.create_task(
                    conn.listen(self._callback), name=f"ws_conn_{conn.conn_id}"
                )
                self._listener_tasks.append(task)

        logger.info(
            "Added %d tokens (total: %d across %d connections)",
            len(token_ids),
            sum(len(c._tokens) for c in self._connections),
            len(self._connections),
        )

    async def remove_tokens(self, token_ids: list[str]):
        if not token_ids:
            return
        by_conn: dict[int, list[str]] = {}
        for tok in token_ids:
            conn = self._token_to_conn.pop(tok, None)
            if conn:
                by_conn.setdefault(conn.conn_id, []).append(tok)
        for conn in self._connections:
            tokens = by_conn.get(conn.conn_id, [])
            if tokens:
                await conn.remove_tokens(tokens)
        logger.info(
            "Removed %d tokens (total: %d across %d connections)",
            len(token_ids),
            sum(len(c._tokens) for c in self._connections),
            len(self._connections),
        )

    async def listen(self, callback: Callable):
        self._callback = callback
        self._listen_event = asyncio.Event()
        for conn in self._connections:
            task = asyncio.create_task(
                conn.listen(callback), name=f"ws_conn_{conn.conn_id}"
            )
            self._listener_tasks.append(task)
        try:
            await self._listen_event.wait()
        except asyncio.CancelledError:
            for task in self._listener_tasks:
                task.cancel()
            await asyncio.gather(*self._listener_tasks, return_exceptions=True)
            return

    def get_status(self) -> dict:
        now = time.time()
        total_messages = sum(c._total_messages for c in self._connections)
        reconnect_count = sum(c._reconnect_count for c in self._connections)
        total_tokens = sum(len(c._tokens) for c in self._connections)

        last_msg_times = [c._last_message_time for c in self._connections if c._last_message_time]
        last_message_time = max(last_msg_times) if last_msg_times else 0.0

        events_by_type: dict[str, int] = {}
        for conn in self._connections:
            for k, v in conn._events_by_type.items():
                events_by_type[k] = events_by_type.get(k, 0) + v

        rate = sum(
            c._messages_last_sec / max(now - c._last_rate_calc, 0.001)
            for c in self._connections
            if c._last_rate_calc and now - c._last_rate_calc < 2.0
        )

        uptimes = [
            now - c._connect_time
            for c in self._connections
            if c._connect_time and c.state == WsState.CONNECTED
        ]
        uptime = round(max(uptimes), 1) if uptimes else 0

        return {
            "state": self.state.value,
            "uptime_seconds": uptime,
            "reconnect_count": reconnect_count,
            "messages_per_sec": round(rate, 1),
            "subscribed_tokens": total_tokens,
            "last_message_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last_message_time))
                if last_message_time
                else None
            ),
            "total_messages": total_messages,
            "events_by_type": events_by_type,
            "connections": len(self._connections),
            "tokens_per_connection": [len(c._tokens) for c in self._connections],
        }

    async def close(self):
        for task in self._listener_tasks:
            task.cancel()
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()
        for conn in self._connections:
            await conn.close()
        self._connections.clear()
        self._token_to_conn.clear()

    def _create_connection(self) -> _WebSocketConnection:
        conn = _WebSocketConnection(self._next_conn_id)
        self._next_conn_id += 1
        self._connections.append(conn)
        return conn

    @staticmethod
    def _parse_event(data: dict):
        return _parse_event(data)
