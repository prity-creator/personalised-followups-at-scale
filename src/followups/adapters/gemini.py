"""Google Gemini: a one page visual answering an objection.

Docs: https://ai.google.dev/gemini-api/docs/image-generation

The model returns the image inline as base64, so there is nothing to download
afterwards. The bytes are written next to the other generated assets.
"""

from __future__ import annotations

import base64
from pathlib import Path

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-image"


class GeminiVisualGenerator(RealAdapter):
    ENV_KEY = "GEMINI_API_KEY"
    EXTRA_ENV = {"GEMINI_MODEL": "model"}
    track = Track.VISUAL

    def __init__(
        self,
        api_key: str,
        http=None,
        out_dir: Path | str = "assets",
        model: str = DEFAULT_MODEL,
        **options,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        self.out_dir = Path(out_dir)
        self.model = model

    def generate(self, brief: AssetBrief) -> Asset:
        payload = self.http.request(
            "POST",
            f"{API_ROOT}/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json_body={"contents": [{"parts": [{"text": self._prompt(brief)}]}]},
        ).json()

        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise RuntimeError(f"gemini blocked the prompt: {blocked}")

        data, mime = self._first_image(payload)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        extension = mime.split("/")[-1] or "png"
        path = self.out_dir / f"visual-{brief.reply.id}.{extension}"
        path.write_bytes(base64.b64decode(data))

        return Asset(
            track=Track.VISUAL,
            url=path.as_uri(),
            title=f"{brief.prospect.company}: one page on that",
            preview_path=str(path),
        )

    @staticmethod
    def _first_image(payload: dict) -> tuple[str, str]:
        for candidate in payload.get("candidates", []):
            for part in (candidate.get("content") or {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return inline["data"], inline.get("mimeType", "image/png")
        raise RuntimeError(f"gemini returned no image: {payload}")

    @staticmethod
    def _prompt(brief: AssetBrief) -> str:
        p = brief.prospect
        return (
            f"Design a single clean infographic, 1200 by 675 pixels, for a business "
            f"audience.\n\n"
            f"Audience: {p.name}, {p.role} at {p.company}.\n"
            f'They pushed back on a sales message saying: "{brief.reply.text}"\n\n'
            f"The graphic must answer that specific point in at most 25 words of text, "
            f"laid out as a short headline and three supporting labels. Flat colours, "
            f"generous whitespace, no stock photography, no logos, no invented "
            f"statistics, no fake company names. All text must be spelled correctly."
        )
