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


class WebSocketManager:
    def __init__(self):
        self.state: WsState = WsState.DISCONNECTED
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscribed_tokens: set[str] = set()
        self._reconnect_delay: float = config.RECONNECT_INITIAL_DELAY
        self._connect_time: float = 0.0

        self._total_messages: int = 0
        self._messages_last_sec: int = 0
        self._messages_per_sec: float = 0.0
        self._last_message_time: float = 0.0
        self._reconnect_count: int = 0
        self._events_by_type: dict[str, int] = {}
        self._last_rate_calc: float = 0.0

    async def connect(self):
        logger.info("Connecting to %s", config.WS_URL)
        self._ws = await websockets.connect(config.WS_URL)
        self.state = WsState.CONNECTED
        self._connect_time = time.time()
        self._reconnect_delay = config.RECONNECT_INITIAL_DELAY
        logger.info("WebSocket connected")

    async def subscribe(self, token_ids: list[str]):
        if not self._ws:
            raise RuntimeError("Not connected")
        msg = {
            "assets_ids": token_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }
        await self._ws.send(json.dumps(msg))
        self._subscribed_tokens.update(token_ids)
        logger.info("Subscribed to %d tokens", len(token_ids))

    async def add_tokens(self, token_ids: list[str]):
        if not self._ws or not token_ids:
            return
        msg = {
            "assets_ids": token_ids,
            "operation": "subscribe",
            "custom_feature_enabled": True,
        }
        await self._ws.send(json.dumps(msg))
        self._subscribed_tokens.update(token_ids)
        logger.info("Added %d tokens (total: %d)", len(token_ids), len(self._subscribed_tokens))

    async def remove_tokens(self, token_ids: list[str]):
        if not self._ws or not token_ids:
            return
        msg = {
            "assets_ids": token_ids,
            "operation": "unsubscribe",
        }
        await self._ws.send(json.dumps(msg))
        self._subscribed_tokens.difference_update(token_ids)
        logger.info("Removed %d tokens (total: %d)", len(token_ids), len(self._subscribed_tokens))

    async def listen(self, callback: Callable):
        while True:
            try:
                await self._listen_loop(callback)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning("WebSocket disconnected: %s", e)
                self.state = WsState.RECONNECTING
                await self._handle_reconnect(callback)
            except asyncio.CancelledError:
                logger.info("WebSocket listener cancelled")
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
                        event = self._parse_event(item)
                        if event:
                            await callback(event)
                else:
                    event = self._parse_event(data)
                    if event:
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

    async def _handle_reconnect(self, callback: Callable):
        disconnect_start = time.time()
        disconnect_notified = False

        while True:
            logger.info("Reconnecting in %.1fs (attempt %d)", self._reconnect_delay, self._reconnect_count + 1)
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * config.RECONNECT_MULTIPLIER,
                config.RECONNECT_MAX_DELAY,
            )
            self._reconnect_count += 1

            try:
                await self.connect()
                if self._subscribed_tokens:
                    await self.subscribe(list(self._subscribed_tokens))
                logger.info("Reconnected and resubscribed to %d tokens", len(self._subscribed_tokens))
                return
            except Exception as e:
                logger.error("Reconnect failed: %s", e)

            elapsed = time.time() - disconnect_start
            if elapsed > 30 and not disconnect_notified:
                logger.error("Disconnected for >30s — emitting DISCONNECT event")
                await callback("DISCONNECT")
                disconnect_notified = True

    def _parse_event(self, data: dict):
        event_type = data.get("event_type", "")
        self._events_by_type[event_type] = self._events_by_type.get(event_type, 0) + 1

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
            except (KeyError, ValueError) as e:
                logger.debug("Failed to parse best_bid_ask: %s", e)
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
            except (KeyError, ValueError) as e:
                logger.debug("Failed to parse last_trade_price: %s", e)
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
            except (KeyError, ValueError, IndexError) as e:
                logger.debug("Failed to parse book: %s", e)
                return None

        return None

    def _update_rate(self):
        now = time.time()
        if now - self._last_rate_calc >= 1.0:
            self._messages_per_sec = self._messages_last_sec / max(now - self._last_rate_calc, 0.001)
            self._messages_last_sec = 0
            self._last_rate_calc = now

    def get_status(self) -> dict:
        now = time.time()
        if self._last_rate_calc and now - self._last_rate_calc < 2.0:
            rate = self._messages_last_sec / max(now - self._last_rate_calc, 0.001)
        else:
            rate = 0.0

        return {
            "state": self.state.value,
            "uptime_seconds": (
                round(now - self._connect_time, 1)
                if self._connect_time and self.state == WsState.CONNECTED
                else 0
            ),
            "reconnect_count": self._reconnect_count,
            "messages_per_sec": round(rate, 1),
            "subscribed_tokens": len(self._subscribed_tokens),
            "last_message_at": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._last_message_time))
                if self._last_message_time else None
            ),
            "total_messages": self._total_messages,
            "events_by_type": dict(self._events_by_type),
        }

    async def close(self):
        if self._ws:
            await self._ws.close()
            self._ws = None
        self.state = WsState.DISCONNECTED
