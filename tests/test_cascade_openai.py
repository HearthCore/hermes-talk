"""OpenAI-compatible cascade TTS lane — REST transport, fail-closed config.

No network, no real keys: the transport is a scripted fake request callable
and every key in this file is a literal placeholder. Mirrors the coverage
shape of ``test_cascade_voice.py``'s ElevenLabs suite but for the REST
(one-call-per-chunk) transport instead of the stream-input WebSocket.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

import talk_cascade_voice as cascade
import talk_config
import talk_doctor
import talk_realtime as rt

FAKE_KEY = "fake-openai-compatible-key-for-tests"
FAKE_VOICE = "fake-voice-for-tests"
FAKE_MODEL = "fake-tts-model"
FAKE_BASE_URL = "http://tts.invalid/v1"


def _scrub_cascade_env(monkeypatch):
    """Make cascade config resolution hermetic on a box with real keys set."""

    for name in (
        "TALK_VOICE_MODE",
        "TALK_CASCADE_TTS",
        "TALK_PROVIDER",
        "TALK_ELEVENLABS_API_KEY",
        "ELEVENLABS_API_KEY",
        "TALK_ELEVENLABS_VOICE_ID",
        "TALK_ELEVENLABS_MODEL",
        "TALK_CASCADE_OPENAI_BASE_URL",
        "TALK_CASCADE_OPENAI_API_KEY",
        "TALK_CASCADE_OPENAI_MODEL",
        "TALK_CASCADE_OPENAI_VOICE",
        "TALK_OPENAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Fail-closed config resolution
# ---------------------------------------------------------------------------


def test_cascade_tts_accepts_openai(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    assert talk_config.cascade_tts() == "openai"


def test_openai_base_url_required(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    with pytest.raises(talk_config.TalkConfigError, match="TALK_CASCADE_OPENAI_BASE_URL"):
        talk_config.cascade_openai_base_url()


def test_openai_base_url_strips_trailing_slash(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_BASE_URL", "https://gateway.example/v1/")
    assert talk_config.cascade_openai_base_url() == "https://gateway.example/v1"


def test_openai_model_required(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    with pytest.raises(talk_config.TalkConfigError, match="TALK_CASCADE_OPENAI_MODEL"):
        talk_config.cascade_openai_model()


def test_openai_voice_required(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    with pytest.raises(talk_config.TalkConfigError, match="TALK_CASCADE_OPENAI_VOICE"):
        talk_config.cascade_openai_voice()


def test_openai_key_optional_when_all_unset(monkeypatch):
    """A self-hosted endpoint that needs no key: every var absent -> ''."""

    _scrub_cascade_env(monkeypatch)
    assert talk_config.resolve_cascade_openai_key() == ""


@pytest.mark.parametrize(
    "env_name",
    ["TALK_CASCADE_OPENAI_API_KEY", "TALK_OPENAI_API_KEY", "OPENAI_API_KEY"],
)
def test_openai_key_set_but_blank_refuses(monkeypatch, env_name):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv(env_name, "")
    with pytest.raises(talk_config.TalkConfigError):
        talk_config.resolve_cascade_openai_key()


def test_openai_key_precedence_cascade_scoped_wins(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_API_KEY", "cascade-scoped")
    monkeypatch.setenv("TALK_OPENAI_API_KEY", "talk-scoped")
    monkeypatch.setenv("OPENAI_API_KEY", "shared")
    assert talk_config.resolve_cascade_openai_key() == "cascade-scoped"


def test_openai_key_precedence_falls_back_to_talk_scoped(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_OPENAI_API_KEY", "talk-scoped")
    monkeypatch.setenv("OPENAI_API_KEY", "shared")
    assert talk_config.resolve_cascade_openai_key() == "talk-scoped"


def test_openai_key_precedence_falls_back_to_shared(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "shared")
    assert talk_config.resolve_cascade_openai_key() == "shared"


def test_cascade_voice_config_resolves_openai_triple(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    monkeypatch.setenv("TALK_CASCADE_OPENAI_BASE_URL", FAKE_BASE_URL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_MODEL", FAKE_MODEL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_VOICE", FAKE_VOICE)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_API_KEY", FAKE_KEY)
    key, voice, model = talk_config.cascade_voice_config("openai")
    assert (key, voice, model) == (FAKE_KEY, FAKE_VOICE, FAKE_MODEL)


def test_cascade_voice_config_still_requires_openai_realtime_provider(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    with pytest.raises(talk_config.TalkConfigError, match="TALK_PROVIDER=openai"):
        talk_config.cascade_voice_config("grok")


# ---------------------------------------------------------------------------
# build_cascade_voice factory
# ---------------------------------------------------------------------------


def test_build_cascade_voice_selects_openai_class():
    voice = cascade.build_cascade_voice(
        tts_provider="openai",
        api_key=FAKE_KEY,
        voice_id=FAKE_VOICE,
        model=FAKE_MODEL,
        on_audio=lambda _: None,
        on_error=lambda _: None,
        base_url=FAKE_BASE_URL,
    )
    assert isinstance(voice, cascade.OpenAICascadeVoice)


def test_build_cascade_voice_selects_elevenlabs_class_by_default():
    voice = cascade.build_cascade_voice(
        tts_provider="elevenlabs",
        api_key=FAKE_KEY,
        voice_id=FAKE_VOICE,
        model=FAKE_MODEL,
        on_audio=lambda _: None,
        on_error=lambda _: None,
    )
    assert type(voice) is cascade.CascadeVoice


def test_build_cascade_voice_openai_without_base_url_refuses():
    with pytest.raises(cascade.CascadeTTSError, match="base_url"):
        cascade.build_cascade_voice(
            tts_provider="openai",
            api_key=FAKE_KEY,
            voice_id=FAKE_VOICE,
            model=FAKE_MODEL,
            on_audio=lambda _: None,
            on_error=lambda _: None,
        )


# ---------------------------------------------------------------------------
# OpenAICascadeVoice transport (fake request callable, no network)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body


class _FakeRequestFactory:
    """A scripted ``request(url=..., headers=..., json=...) -> bytes`` seam.

    Records every call so tests can assert on payload shape, and returns
    canned PCM bytes (or raises) per a caller-supplied response queue.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def __call__(self, *, url, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _voice(request_factory, *, api_key=FAKE_KEY, on_audio=None, on_error=None, on_stream_end=None):
    return cascade.OpenAICascadeVoice(
        api_key=api_key,
        voice=FAKE_VOICE,
        model=FAKE_MODEL,
        base_url=FAKE_BASE_URL,
        on_audio=on_audio or (lambda _: None),
        on_error=on_error or (lambda _: None),
        on_stream_end=on_stream_end,
        request=request_factory,
    )


def test_one_rest_call_per_chunk_with_correct_payload_shape():
    factory = _FakeRequestFactory([b"pcm-bytes-one", b"pcm-bytes-two"])
    received: list[bytes] = []
    ended: list[bool] = []
    voice = _voice(
        factory,
        on_audio=received.append,
        on_stream_end=lambda: ended.append(True),
    )

    async def run():
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="First sentence. Second sentence.",
                response_id="r1",
                final=False,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        voice.handle_event(rt.ResponseFinished(response_id="r1"))
        for _ in range(50):
            await asyncio.sleep(0)
            if ended:
                break
        await voice.aclose()

    asyncio.run(run())

    assert received == [b"pcm-bytes-one", b"pcm-bytes-two"]
    assert len(factory.calls) == 2
    call = factory.calls[0]
    assert call["url"] == f"{FAKE_BASE_URL}/audio/speech"
    assert call["headers"] == {"Authorization": f"Bearer {FAKE_KEY}"}
    assert call["json"] == {
        "model": FAKE_MODEL,
        "voice": FAKE_VOICE,
        "input": "First sentence.",
        "response_format": "pcm",
    }


def test_no_key_sends_no_authorization_header():
    factory = _FakeRequestFactory([b"pcm"])
    voice = _voice(factory, api_key="")

    async def run():
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="Hello.",
                response_id="r1",
                final=True,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        for _ in range(50):
            await asyncio.sleep(0)
            if factory.calls:
                break
        await voice.aclose()

    asyncio.run(run())

    assert factory.calls[0]["headers"] == {}


def test_http_error_status_degrades_to_text_only_receipt():
    factory = _FakeRequestFactory([cascade.CascadeTTSError("TTS endpoint returned HTTP 500")])
    errors: list[str] = []
    voice = _voice(factory, on_error=errors.append)

    async def run():
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="This will fail.",
                response_id="r1",
                final=True,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        for _ in range(50):
            await asyncio.sleep(0)
            if errors:
                break
        await voice.aclose()

    asyncio.run(run())

    assert len(errors) == 1
    assert "staying text-only" in errors[0]


def test_barge_in_cancels_in_flight_request_and_emits_no_audio():
    """A request that is still pending when SpeechStarted fires never resolves
    into audio: the generation check on emission drops it even if the fake
    transport 'completes' after the abort.
    """

    received: list[bytes] = []

    class _SlowFactory:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, url, headers, json):
            self.calls += 1
            # Never resolves until cancelled — simulates an in-flight request
            # at the moment of barge-in.
            await asyncio.Event().wait()

    factory = _SlowFactory()
    voice = _voice(factory, on_audio=received.append)

    async def run():
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="This sentence never finishes synthesizing.",
                response_id="r1",
                final=True,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        await asyncio.sleep(0)  # let the worker pick up the chunk and call in
        for _ in range(20):
            await asyncio.sleep(0)
            if factory.calls:
                break
        voice.handle_event(rt.SpeechStarted())
        await asyncio.sleep(0.05)
        await voice.aclose()

    asyncio.run(run())

    assert received == []
    assert factory.calls == 1


# ---------------------------------------------------------------------------
# Doctor check
# ---------------------------------------------------------------------------


def _wav(samples: bytes, *, rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    """A minimal canonical WAV container around ``samples``.

    What a gateway returns when it ignores ``response_format="pcm"`` —
    LiteLLM in front of a self-hosted TTS model does exactly this, and the
    bytes it wraps are already the 24kHz mono s16le the sink expects.
    """

    fmt = struct.pack(
        "<4sIHHIIHH",
        b"fmt ", 16, 1, channels, rate,
        rate * channels * bits // 8, channels * bits // 8, bits,
    )
    data = struct.pack("<4sI", b"data", len(samples)) + samples
    body = fmt + data
    return struct.pack("<4sI4s", b"RIFF", len(body) + 4, b"WAVE") + body


def _speak_one(request_factory, *, api_key=FAKE_KEY, on_audio=None, on_stream_end=None):
    """One response, one sentence, drained — the shape every container test needs."""

    received: list[bytes] = []
    ended: list[bool] = []

    async def run():
        voice = _voice(
            request_factory,
            api_key=api_key,
            on_audio=on_audio or received.append,
            on_stream_end=lambda: ended.append(True),
        )
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="One sentence.",
                response_id="r1",
                final=True,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        for _ in range(50):
            await asyncio.sleep(0)
            if ended:
                break
        await voice.aclose()

    asyncio.run(run())
    return received


def test_a_wav_wrapped_body_reaches_the_sink_as_bare_samples():
    """The sink is documented as raw PCM: a WAV wrapper must not leak through.

    Those 44 header bytes played as samples click at the start of every
    sentence, and a container that disagreed with 24kHz mono s16le would
    corrupt the whole answer instead of clicking once.
    """

    samples = b"\x01\x02\x03\x04" * 40
    received = _speak_one(_FakeRequestFactory([_wav(samples)]))

    assert received == [samples]
    assert received[0][:4] != b"RIFF"


def test_a_raw_pcm_body_is_never_parsed():
    """The common case — an endpoint that honours response_format=pcm."""

    raw = b"\x7f\x00\xff\x7f" * 32
    assert _speak_one(_FakeRequestFactory([raw])) == [raw]


def test_a_body_that_merely_starts_with_riff_but_has_no_data_chunk_passes_through():
    """Unrecognised container: emit it unchanged rather than emit silence.

    Silence would be indistinguishable from a working session with a quiet
    voice; a click is at least evidence of what actually arrived.
    """

    body = struct.pack("<4sI4s", b"RIFF", 40, b"WAVE") + b"junk-chunk-without-data"
    assert _speak_one(_FakeRequestFactory([body])) == [body]


def test_each_chunk_of_a_multi_sentence_answer_is_unwrapped_independently():
    """One container per request, so the unwrap is per chunk, not per response."""

    first = b"\x11\x22" * 24
    second = b"\x33\x44" * 24

    # Two sentences, so the chunker splits and each request carries its own
    # container: the unwrap has to happen per chunk, not once per response.
    factory = _FakeRequestFactory([_wav(first), _wav(second)])
    received: list[bytes] = []
    ended: list[bool] = []

    async def run():
        voice = _voice(factory, on_audio=received.append, on_stream_end=lambda: ended.append(True))
        voice.start()
        voice.handle_event(rt.ResponseStarted(response_id="r1"))
        voice.handle_event(
            rt.Transcript(
                role=rt.TranscriptRole.ASSISTANT,
                text="First sentence. Second sentence.",
                response_id="r1",
                final=False,
                provenance=rt.TranscriptProvenance.OUTPUT_AUDIO,
            )
        )
        voice.handle_event(rt.ResponseFinished(response_id="r1"))
        for _ in range(50):
            await asyncio.sleep(0)
            if ended:
                break
        await voice.aclose()

    asyncio.run(run())

    assert received == [first, second]
    assert len(factory.calls) == 2


def test_doctor_cascade_check_openai_pass(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_VOICE_MODE", "cascade")
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    monkeypatch.setenv("TALK_PROVIDER", "openai")
    monkeypatch.setenv("TALK_CASCADE_OPENAI_BASE_URL", FAKE_BASE_URL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_MODEL", FAKE_MODEL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_VOICE", FAKE_VOICE)
    result = talk_doctor._cascade_check()
    assert result["status"] == "pass"
    assert result["details"]["tts"] == "openai"
    assert result["details"]["base_url"] == FAKE_BASE_URL


def test_doctor_cascade_check_openai_missing_base_url_fails(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_VOICE_MODE", "cascade")
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    monkeypatch.setenv("TALK_PROVIDER", "openai")
    monkeypatch.setenv("TALK_CASCADE_OPENAI_MODEL", FAKE_MODEL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_VOICE", FAKE_VOICE)
    result = talk_doctor._cascade_check()
    assert result["status"] == "fail"
    assert "base URL" in result["summary"]


def test_doctor_cascade_check_openai_wrong_realtime_provider_fails(monkeypatch):
    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_VOICE_MODE", "cascade")
    monkeypatch.setenv("TALK_CASCADE_TTS", "openai")
    monkeypatch.setenv("TALK_PROVIDER", "grok")
    monkeypatch.setenv("TALK_CASCADE_OPENAI_BASE_URL", FAKE_BASE_URL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_MODEL", FAKE_MODEL)
    monkeypatch.setenv("TALK_CASCADE_OPENAI_VOICE", FAKE_VOICE)
    result = talk_doctor._cascade_check()
    assert result["status"] == "fail"
    assert "requires the openai provider" in result["summary"]


def test_doctor_cascade_check_still_covers_elevenlabs(monkeypatch):
    """The refactor must not regress the original ElevenLabs check."""

    _scrub_cascade_env(monkeypatch)
    monkeypatch.setenv("TALK_VOICE_MODE", "cascade")
    monkeypatch.setenv("TALK_PROVIDER", "openai")
    monkeypatch.setenv("TALK_ELEVENLABS_API_KEY", FAKE_KEY)
    monkeypatch.setenv("TALK_ELEVENLABS_VOICE_ID", FAKE_VOICE)
    result = talk_doctor._cascade_check()
    assert result["status"] == "pass"
    assert result["details"]["tts"] == "elevenlabs"
