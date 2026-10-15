from __future__ import annotations

import base64

import pytest

from followups.adapters.gemini import GeminiVisualGenerator
from followups.domain.models import AssetBrief, Category, Track
from tests.conftest import make_classification, make_prospect, make_reply
from tests.fakes import FakeHttpClient, ok

PNG = b"\x89PNG\r\n\x1a\nfake"


def brief(category: Category = Category.OBJECTION) -> AssetBrief:
    return AssetBrief(make_prospect(), make_reply(), make_classification(category))


def image_response(data: bytes = PNG, mime: str = "image/png") -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
                    ]
                }
            }
        ]
    }


def test_posts_to_generate_content_with_the_google_key_header(tmp_path):
    http = FakeHttpClient(responses=[ok(image_response())])
    GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())
    call = http.calls[0]
    assert "generativelanguage.googleapis.com" in call.url
    assert call.url.endswith(":generateContent")
    assert call.headers["x-goog-api-key"] == "key"


def test_the_prompt_answers_the_specific_objection(tmp_path):
    http = FakeHttpClient(responses=[ok(image_response())])
    GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())
    prompt = http.calls[0].json_body["contents"][0]["parts"][0]["text"]
    assert "sounds good" in prompt
    assert "Analytical Co" in prompt


def test_the_decoded_image_is_written_to_disk(tmp_path):
    http = FakeHttpClient(responses=[ok(image_response())])
    asset = GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())
    assert asset.track is Track.VISUAL
    written = tmp_path / asset.preview_path.rsplit("/", 1)[-1]
    assert written.read_bytes() == PNG


def test_the_file_extension_follows_the_returned_mime_type(tmp_path):
    http = FakeHttpClient(responses=[ok(image_response(mime="image/jpeg"))])
    asset = GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())
    assert asset.preview_path.endswith(".jpeg")


def test_a_response_with_no_image_raises_clearly(tmp_path):
    empty = {"candidates": [{"content": {"parts": [{"text": "I cannot do that"}]}}]}
    http = FakeHttpClient(responses=[ok(empty)])
    with pytest.raises(RuntimeError, match="no image"):
        GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())


def test_a_blocked_prompt_raises_with_the_reason(tmp_path):
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
    http = FakeHttpClient(responses=[ok(blocked)])
    with pytest.raises(RuntimeError, match="SAFETY"):
        GeminiVisualGenerator("key", http=http, out_dir=tmp_path).generate(brief())
