"""Bounded, per-client live event fanout for WebSocket consumers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class _Client:
    socket: WebSocket
    queue: asyncio.Queue[dict[str, Any]]
    sender: asyncio.Task[None] | None = None
    eviction_pending: bool = False
    eviction_task: asyncio.Task[None] | None = None


class WebSocketHub:
    """Queue events per socket so a slow browser cannot block other clients."""

    def __init__(self, queue_size: int = 32, send_timeout_seconds: float = 2.0):
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        if send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        self.queue_size = queue_size
        self.send_timeout_seconds = send_timeout_seconds
        self._clients: dict[WebSocket, _Client] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        client = _Client(socket, asyncio.Queue(maxsize=self.queue_size))
        self._clients[socket] = client
        client.sender = asyncio.create_task(self._send_loop(client))

    async def disconnect(
        self, socket: WebSocket, *, code: int = 1013, close: bool = True
    ) -> None:
        client = self._clients.pop(socket, None)
        if client is None:
            return
        sender = client.sender
        if sender is not None and sender is not asyncio.current_task():
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        if close:
            try:
                await asyncio.wait_for(
                    socket.close(code=code), timeout=self.send_timeout_seconds
                )
            except Exception:
                pass

    def publish(self, envelope: dict[str, Any]) -> None:
        """Enqueue an event without awaiting any client network operation."""
        for socket, client in list(self._clients.items()):
            if client.eviction_pending:
                continue
            try:
                client.queue.put_nowait(envelope)
            except asyncio.QueueFull:
                client.eviction_pending = True
                client.eviction_task = asyncio.create_task(
                    self.disconnect(socket, code=1013)
                )

    async def _send_loop(self, client: _Client) -> None:
        try:
            while True:
                envelope = await client.queue.get()
                await asyncio.wait_for(
                    client.socket.send_json(envelope),
                    timeout=self.send_timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.disconnect(client.socket, code=1013)
