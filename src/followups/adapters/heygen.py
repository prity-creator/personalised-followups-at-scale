"""HeyGen plus ElevenLabs: a short personalised video for people asking to meet.

Docs: https://docs.heygen.com/reference/create-an-avatar-video-v2
      https://elevenlabs.io/docs/api-reference/text-to-speech

Two vendors, one port. HeyGen renders the avatar and speaks the script; the
voice is chosen by `voice_id`, which may be an ElevenLabs voice configured
inside HeyGen. `ElevenLabsVoice` is separate and optional, for when you want the
audio on its own rather than inside a video.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

TERMINAL_FAILURES = {"failed", "error"}

#: Roughly 45 seconds of speech. Past this people stop watching, and HeyGen
#: charges by the second.
MAX_SPOKEN_WORDS = 130


class HeyGenVideoGenerator(RealAdapter):
    ENV_KEY = "HEYGEN_API_KEY"
    EXTRA_ENV = {"HEYGEN_AVATAR_ID": "avatar_id", "HEYGEN_VOICE_ID": "voice_id"}
    track = Track.VIDEO

    def __init__(
        self,
        api_key: str,
        http=None,
        sleep: Callable[[float], None] = time.sleep,
        avatar_id: str = "default",
        voice_id: str = "default",
        max_polls: int = 60,
        poll_seconds: float = 5.0,
        **options,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        self._sleep = sleep
        self.avatar_id = avatar_id
        self.voice_id = voice_id
        self.max_polls = max_polls
        self.poll_seconds = poll_seconds

    def generate(self, brief: AssetBrief) -> Asset:
        video_id = self._start(brief)
        url = self._await_completion(video_id)
        return Asset(
            track=Track.VIDEO,
            url=url,
            title=f"{brief.prospect.company}: 40 seconds before we talk",
            preview_path="",
        )

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key}

    def _start(self, brief: AssetBrief) -> str:
        payload = self.http.request(
            "POST",
            HEYGEN_GENERATE_URL,
            headers=self._headers(),
            json_body={
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": self.avatar_id,
                            "avatar_style": "normal",
                        },
                        "voice": {
                            "type": "text",
                            "input_text": self.script(brief),
                            "voice_id": self.voice_id,
                        },
                    }
                ],
                "dimension": {"width": 1280, "height": 720},
            },
        ).json()
        video_id = (payload.get("data") or {}).get("video_id")
        if not video_id:
            raise RuntimeError(f"heygen did not return a video_id: {payload}")
        return video_id

    def _await_completion(self, video_id: str) -> str:
        for _ in range(self.max_polls):
            payload = self.http.request(
                "GET", f"{HEYGEN_STATUS_URL}?video_id={video_id}", headers=self._headers()
            ).json()
            data = payload.get("data") or {}
            status = str(data.get("status", "")).lower()

            if status == "completed":
                url = data.get("video_url")
                if not url:
                    raise RuntimeError(f"heygen completed without a url: {payload}")
                return url

            if status in TERMINAL_FAILURES:
                reason = (data.get("error") or {}).get("message", status)
                raise RuntimeError(f"heygen render failed: {reason}")

            self._sleep(self.poll_seconds)

        raise RuntimeError(f"heygen video {video_id} did not finish within {self.max_polls} polls")

    @staticmethod
    def script(brief: AssetBrief) -> str:
        """What the avatar says. Truncated, because length costs money and attention."""
        p = brief.prospect
        first_name = (p.name.split() or ["there"])[0]
        quoted = " ".join(brief.reply.text.split()[:25])
        text = (
            f"Hi {first_name}, thanks for getting back to me. "
            f'You said "{quoted}". '
            f"Rather than send you a wall of text, here is the short version of what "
            f"we would actually do for {p.company}, and then you can decide whether a "
            f"call is worth your time."
        )
        words = text.split()
        if len(words) <= MAX_SPOKEN_WORDS:
            return text
        return " ".join(words[:MAX_SPOKEN_WORDS])


class ElevenLabsVoice(RealAdapter):
    """Optional: the script as an audio file, without a video around it."""

    ENV_KEY = "ELEVENLABS_API_KEY"
    EXTRA_ENV = {"ELEVENLABS_VOICE_ID": "voice_id"}

    def __init__(
        self,
        api_key: str,
        http=None,
        voice_id: str = "default",
        model_id: str = "eleven_multilingual_v2",
        **options,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        self.voice_id = voice_id
        self.model_id = model_id

    def synthesize(self, text: str, out_dir: Path | str) -> Path:
        response = self.http.request(
            "POST",
            f"{ELEVENLABS_URL}/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
            json_body={"text": text, "model_id": self.model_id},
        )
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"voice-{abs(hash(text)) % 10**10}.mp3"
        path.write_bytes(response.body)
        return path
