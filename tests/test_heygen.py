from __future__ import annotations

import pytest

from followups.adapters.heygen import ElevenLabsVoice, HeyGenVideoGenerator
from followups.domain.models import AssetBrief, Track
from tests.conftest import make_classification, make_prospect, make_reply
from tests.fakes import FakeHttpClient, ok, raw


def brief() -> AssetBrief:
    return AssetBrief(make_prospect(), make_reply(), make_classification())


def generator(http, **kw):
    return HeyGenVideoGenerator("key", http=http, sleep=lambda _s: None, **kw)


def started(vid="v1") -> dict:
    return {"data": {"video_id": vid}}


def state(status, url="https://heygen.invalid/v1.mp4") -> dict:
    data = {"status": status}
    if status == "completed":
        data["video_url"] = url
    return {"data": data}


def test_posts_to_the_v2_generate_endpoint():
    http = FakeHttpClient(responses=[ok(started()), ok(state("completed"))])
    generator(http).generate(brief())
    call = http.calls[0]
    assert call.url == "https://api.heygen.com/v2/video/generate"
    assert call.headers["X-Api-Key"] == "key"


def test_the_script_is_personalised_and_spoken_by_the_configured_voice():
    http = FakeHttpClient(responses=[ok(started()), ok(state("completed"))])
    generator(http, voice_id="voice-abc").generate(brief())
    voice = http.calls[0].json_body["video_inputs"][0]["voice"]
    assert voice["voice_id"] == "voice-abc"
    assert "Ada" in voice["input_text"]
    assert "Analytical Co" in voice["input_text"]


def test_polls_the_status_endpoint_until_completed():
    http = FakeHttpClient(
        responses=[ok(started()), ok(state("processing")), ok(state("completed"))]
    )
    asset = generator(http).generate(brief())
    assert "video_status.get?video_id=v1" in http.calls[1].url
    assert asset.url == "https://heygen.invalid/v1.mp4"
    assert asset.track is Track.VIDEO


def test_a_failed_render_raises_with_the_reason():
    failed = {"data": {"status": "failed", "error": {"message": "avatar not found"}}}
    http = FakeHttpClient(responses=[ok(started()), ok(failed)])
    with pytest.raises(RuntimeError, match="avatar not found"):
        generator(http).generate(brief())


def test_gives_up_after_the_poll_budget():
    http = FakeHttpClient(responses=[ok(started())] + [ok(state("processing"))] * 10)
    with pytest.raises(RuntimeError, match="did not finish"):
        generator(http, max_polls=3).generate(brief())


def test_a_start_with_no_video_id_raises():
    http = FakeHttpClient(responses=[ok({"data": {}})])
    with pytest.raises(RuntimeError, match="video_id"):
        generator(http).generate(brief())


def test_script_stays_within_the_spoken_word_budget():
    long_reply = make_reply(text="x " * 500)
    http = FakeHttpClient(responses=[ok(started()), ok(state("completed"))])
    generator(http).generate(
        AssetBrief(make_prospect(), long_reply, make_classification())
    )
    spoken = http.calls[0].json_body["video_inputs"][0]["voice"]["input_text"]
    assert len(spoken.split()) <= 130


def test_elevenlabs_posts_the_script_and_returns_audio(tmp_path):
    http = FakeHttpClient(responses=[raw(b"ID3audio", content_type="audio/mpeg")])
    path = ElevenLabsVoice("key", http=http, voice_id="v9").synthesize("hello there", tmp_path)
    assert http.calls[0].url == "https://api.elevenlabs.io/v1/text-to-speech/v9"
    assert http.calls[0].headers["xi-api-key"] == "key"
    assert http.calls[0].json_body["text"] == "hello there"
    assert path.read_bytes() == b"ID3audio"
