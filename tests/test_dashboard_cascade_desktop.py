"""Desktop cascade lane — the plugin's two-door relay, server-side only.

The desktop plugin cannot stream an upload (its REST door answers JSON, routed
through the app's main process), so the cascade takes one direction per door:
the model's text arrives on ``POST /cascade-feed``, the PCM24k leaves on the
plugin's own WebSocket twin at ``GET /cascade-tts``. What is proved here,
offline: the socket gate never fails open, a stream only exists while its
socket does, an operator barge-in cancels the TTS instead of flushing it, and
the PCM the plugin receives is the PCM the cascade produced — the same
pipeline the browser tab's HTTP lane runs, reached through the other door.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from test_dashboard_api import api
from test_dashboard_cascade import (
    FAKE_KEY,
    FAKE_VOICE_ID,
    JsonRequest,
    _FakeClient,
    _wait_for,
)
from test_dashboard_cascade import tts as _cascade_tts  # noqa: F401 — a fixture, used below

import talk_config  # noqa: F401 — the module the relay resolves its knobs from


@pytest.fixture
def tts(_cascade_tts):  # noqa: F811 — shadows the import on purpose
    """The fake cascade-TTS module, re-exposed under this module's own name.

    Imported instead of re-written: this lane stands up the same
    ``talk_cascade_voice`` seam as the HTTP lane's tests, and a second copy of
    that fake would be a second thing to keep in step with the class it
    stands in for.
    """

    return _cascade_tts


@pytest.fixture(autouse=True)
def _cascade_env(monkeypatch, tmp_path):
    """Cascade configured, dashboard token unset, real operator keys scrubbed."""

    monkeypatch.delenv(api.DASHBOARD_TOKEN_ENV, raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("TALK_PROVIDER", raising=False)
    monkeypatch.setenv("TALK_VOICE_MODE", "cascade")
    monkeypatch.setenv("TALK_ELEVENLABS_API_KEY", FAKE_KEY)
    monkeypatch.setenv("TALK_ELEVENLABS_VOICE_ID", FAKE_VOICE_ID)
    monkeypatch.setenv("TALK_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))


STREAM = "stream-under-test"


class FakeSocket:
    """The slice of a Starlette WebSocket this route touches.

    ``receive`` blocks the way the real one does, so the route's close watcher
    is a real task here — a test drives a disconnect by feeding the frame.
    """

    def __init__(self, *, query=None, headers=None, host="127.0.0.1") -> None:
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.query_params = dict(query if query is not None else {"stream": STREAM})
        self.client = _FakeClient(host) if host is not None else None
        self.accepted = False
        self.close_codes: list[int] = []
        self.sent: list[dict] = []
        self._incoming: asyncio.Queue = asyncio.Queue()

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_codes.append(code)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive(self) -> dict:
        return await self._incoming.get()

    def disconnect(self) -> None:
        self._incoming.put_nowait({"type": "websocket.disconnect"})


def frames(socket: FakeSocket) -> list[dict]:
    return [frame for frame in socket.sent if "pcm" in frame]


async def feed(request_body: dict) -> dict:
    return await api.cascade_feed(JsonRequest(request_body))


def _run(coro):
    return asyncio.run(coro)


# -- the gates ----------------------------------------------------------------


def test_socket_refuses_a_remote_peer_without_a_token():
    socket = FakeSocket(host="203.0.113.9")

    _run(api.cascade_tts_socket(socket))

    assert socket.close_codes == [1008]
    assert socket.accepted is False


def test_socket_demands_the_configured_token(monkeypatch):
    monkeypatch.setenv(api.DASHBOARD_TOKEN_ENV, "s3cret")
    socket = FakeSocket()

    _run(api.cascade_tts_socket(socket))

    assert socket.close_codes == [1008]
    assert socket.accepted is False


def test_socket_accepts_the_token_as_a_query_parameter(monkeypatch):
    """A WebSocket cannot carry the header, so the token rides the query."""

    monkeypatch.setenv(api.DASHBOARD_TOKEN_ENV, "s3cret")
    socket = FakeSocket(query={"stream": STREAM, "talk_token": "s3cret"})

    async def scenario():
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        socket.disconnect()
        await asyncio.wait_for(task, 2)

    _run(scenario())

    assert socket.accepted is True
    assert socket.close_codes == []


def test_socket_carries_a_talk_token_and_a_core_token_side_by_side():
    """The plugin's own gate and the app's connection token share the query."""

    socket = FakeSocket(query={"stream": STREAM, "talk_token": "", "token": "core-token"})

    async def scenario():
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        socket.disconnect()
        await asyncio.wait_for(task, 2)

    _run(scenario())

    assert socket.accepted is True


def test_socket_refuses_without_a_stream_id():
    socket = FakeSocket(query={})

    _run(api.cascade_tts_socket(socket))

    assert socket.close_codes == [1008]


def test_socket_refuses_a_blank_stream_id():
    socket = FakeSocket(query={"stream": "   "})

    _run(api.cascade_tts_socket(socket))

    assert socket.close_codes == [1008]


def test_socket_refuses_a_broken_cascade_knob(monkeypatch, tts):
    monkeypatch.delenv("TALK_ELEVENLABS_VOICE_ID", raising=False)
    socket = FakeSocket()

    _run(api.cascade_tts_socket(socket))

    assert socket.close_codes == [1011]
    assert socket.accepted is False
    assert tts.dials == []  # refused before a secret or socket was spent


def test_socket_refuses_a_second_socket_for_the_same_stream():
    async def scenario():
        first = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(first))
        await _wait_for(lambda: first.accepted)
        second = FakeSocket()
        await api.cascade_tts_socket(second)
        assert second.close_codes == [1013]
        first.disconnect()
        await asyncio.wait_for(task, 2)

    _run(scenario())


def test_feed_refuses_an_unknown_stream():
    with pytest.raises(api.HTTPException) as excinfo:
        _run(feed({"stream": "nobody-is-listening", "delta": "hi"}))

    assert excinfo.value.status_code == 404


def test_feed_refuses_a_line_that_is_neither_delta_nor_done():
    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        with pytest.raises(api.HTTPException) as excinfo:
            await feed({"stream": STREAM, "text": "hi"})
        assert excinfo.value.status_code == 400
        socket.disconnect()
        await asyncio.wait_for(task, 2)

    _run(scenario())


# -- the relay ----------------------------------------------------------------


def test_fed_text_speaks_and_its_pcm_arrives_as_frames(tts):
    """The end-to-end shape: text in over REST, PCM24k out over the socket."""

    pcm_one = b"\x01\x02" * 480
    pcm_two = b"\x03\x04" * 480

    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        await feed({"stream": STREAM, "delta": "First sentence. "})
        await feed({"stream": STREAM, "delta": "Second one. "})
        await feed({"stream": STREAM, "done": "First sentence. Second one."})

        await _wait_for(lambda: len(tts.sockets) == 1)
        ws = tts.sockets[0]
        await _wait_for(lambda: len(ws.sent) == 4)  # BOS, two chunks, EOS
        ws.feed_audio(pcm_one)
        ws.feed_audio(pcm_two)
        ws.feed_final()

        await _wait_for(lambda: socket.sent and socket.sent[-1] == {"end": True})
        socket.disconnect()
        await asyncio.wait_for(task, 2)

        assert [m.get("text") for m in ws.sent] == [
            " ",
            "First sentence.",
            "Second one.",
            "",
        ]
        # The key rides xi-api-key only — never the URL, and never a frame the
        # plugin can read.
        assert tts.dials[0]["headers"] == {"xi-api-key": FAKE_KEY}
        assert FAKE_KEY not in tts.dials[0]["url"]
        joined = b"".join(base64.b64decode(frame["pcm"]) for frame in frames(socket))
        assert joined == pcm_one + pcm_two
        assert FAKE_KEY.encode() not in joined

    _run(scenario())


def test_a_barge_in_cancels_the_tts_instead_of_flushing_it(tts):
    """`{"abort": true}` is the HTTP lane's torn body, as a line."""

    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        await feed({"stream": STREAM, "delta": "An answer the operator talks over. "})

        await _wait_for(lambda: len(tts.sockets) == 1)
        ws = tts.sockets[0]
        await _wait_for(lambda: len(ws.sent) == 2)  # BOS + chunk, never EOS
        pcm = b"\x00\x01" * 240
        ws.feed_audio(pcm)
        await _wait_for(lambda: frames(socket))

        await feed({"stream": STREAM, "abort": True})
        await _wait_for(lambda: ws.closed)
        socket.disconnect()
        await asyncio.wait_for(task, 2)

        assert len(ws.sent) == 2, "EOS went out for an interrupted answer"
        joined = b"".join(base64.b64decode(frame["pcm"]) for frame in frames(socket))
        assert joined == pcm, "audio after the abort point was still spoken"

    _run(scenario())


def test_a_socket_that_goes_away_releases_its_stream(tts):
    """A lost socket must not leave a stream id (or a TTS teardown) behind."""

    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        await feed({"stream": STREAM, "delta": "Half an answer. "})
        socket.disconnect()
        await asyncio.wait_for(task, 2)

        assert STREAM not in api._CASCADE_STREAMS
        with pytest.raises(api.HTTPException) as excinfo:
            await feed({"stream": STREAM, "delta": "text nobody can hear"})
        assert excinfo.value.status_code == 404

    _run(scenario())


def test_the_same_socket_speaks_a_second_response(tts):
    """One socket spans a session: the next answer starts a new speech run."""

    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)

        await feed({"stream": STREAM, "delta": "First answer. "})
        await feed({"stream": STREAM, "done": "First answer."})
        await _wait_for(lambda: len(tts.sockets) == 1)
        tts.sockets[0].feed_audio(b"\x05\x06" * 120)
        tts.sockets[0].feed_final()
        await _wait_for(lambda: socket.sent and socket.sent[-1] == {"end": True})

        await feed({"stream": STREAM, "delta": "Second answer. "})
        await feed({"stream": STREAM, "done": "Second answer."})
        await _wait_for(lambda: len(tts.sockets) == 2)
        tts.sockets[1].feed_audio(b"\x07\x08" * 120)
        tts.sockets[1].feed_final()
        await _wait_for(lambda: len(socket.sent) >= 3 and socket.sent[-1] == {"end": True})

        socket.disconnect()
        await asyncio.wait_for(task, 2)

        assert len(tts.sockets) == 2, "the second response never reached the cascade"
        assert [m.get("text") for m in tts.sockets[1].sent] == [" ", "Second answer.", ""]

    _run(scenario())


def test_an_oversized_feed_line_cancels_rather_than_speaking_half(tts):
    async def scenario():
        socket = FakeSocket()
        task = asyncio.create_task(api.cascade_tts_socket(socket))
        await _wait_for(lambda: socket.accepted)
        await feed({"stream": STREAM, "delta": "A real answer. "})
        await _wait_for(lambda: len(tts.sockets) == 1)

        with pytest.raises(api.HTTPException) as excinfo:
            await feed({"stream": STREAM, "delta": "x" * (api.CASCADE_MAX_LINE_BYTES + 1)})
        assert excinfo.value.status_code == 413
        await _wait_for(lambda: tts.sockets[0].closed)

        socket.disconnect()
        await asyncio.wait_for(task, 2)

    _run(scenario())
