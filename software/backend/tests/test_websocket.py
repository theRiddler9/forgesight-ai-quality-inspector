import asyncio

from software.backend.websocket import WebSocketHub


class FakeWebSocket:
    def __init__(self, block_sends: bool = False):
        self.messages = []
        self.accepted = False
        self.close_code = None
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()
        if not block_sends:
            self.release_send.set()

    async def accept(self):
        self.accepted = True

    async def send_json(self, envelope):
        self.send_started.set()
        await self.release_send.wait()
        self.messages.append(envelope)

    async def close(self, code=1000):
        self.close_code = code


async def wait_for_messages(socket, count):
    for _ in range(100):
        if len(socket.messages) >= count:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"expected {count} messages, received {len(socket.messages)}")


def test_hub_fans_out_and_disconnects_clients_independently():
    async def scenario():
        hub = WebSocketHub(queue_size=2, send_timeout_seconds=0.5)
        first, second = FakeWebSocket(), FakeWebSocket()
        await hub.connect(first)
        await hub.connect(second)

        envelope = {"event": "inspection_result", "data": {"result": "PASS"}}
        hub.publish(envelope)
        await wait_for_messages(first, 1)
        await wait_for_messages(second, 1)
        await hub.disconnect(first, close=False)

        assert first.accepted and second.accepted
        assert first.messages == [envelope]
        assert second.messages == [envelope]
        assert hub.client_count == 1
        await hub.disconnect(second, close=False)

    asyncio.run(scenario())


def test_queue_overflow_evicts_slow_client_without_blocking_healthy_client():
    async def scenario():
        hub = WebSocketHub(queue_size=1, send_timeout_seconds=0.5)
        slow, healthy = FakeWebSocket(block_sends=True), FakeWebSocket()
        await hub.connect(slow)
        await hub.connect(healthy)

        hub.publish({"event": "one", "data": {}})
        await slow.send_started.wait()
        await wait_for_messages(healthy, 1)
        hub.publish({"event": "two", "data": {}})
        await wait_for_messages(healthy, 2)
        hub.publish({"event": "three", "data": {}})
        await wait_for_messages(healthy, 3)
        for _ in range(100):
            if hub.client_count == 1 and slow.close_code == 1013:
                break
            await asyncio.sleep(0.001)

        assert hub.client_count == 1
        assert slow.close_code == 1013
        assert [message["event"] for message in healthy.messages] == ["one", "two", "three"]
        await hub.disconnect(healthy, close=False)

    asyncio.run(scenario())


def test_send_timeout_evicts_only_stalled_client():
    async def scenario():
        hub = WebSocketHub(queue_size=2, send_timeout_seconds=0.01)
        slow, healthy = FakeWebSocket(block_sends=True), FakeWebSocket()
        await hub.connect(slow)
        await hub.connect(healthy)

        hub.publish({"event": "inspection_result", "data": {}})
        await wait_for_messages(healthy, 1)
        for _ in range(100):
            if hub.client_count == 1:
                break
            await asyncio.sleep(0.002)

        assert hub.client_count == 1
        assert slow.close_code == 1013
        assert len(healthy.messages) == 1
        await hub.disconnect(healthy, close=False)

    asyncio.run(scenario())
