"""HeyGen plus ElevenLabs: a short personalised video for people asking to meet."""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

DOCS = "https://docs.heygen.com/reference/create-an-avatar-video-v2"


class HeyGenVideoGenerator(RealAdapter):
    """Voice the script through ElevenLabs, then render it onto an avatar.

    Two services behind one port: the ElevenLabs key is read from
    ELEVENLABS_API_KEY and passed as an option, because the port's consumer
    should not know that the video track needs two vendors.
    """

    ENV_KEY = "HEYGEN_API_KEY"
    VOICE_ENV_KEY = "ELEVENLABS_API_KEY"
    track = Track.VIDEO

    def generate(self, brief: AssetBrief) -> Asset:
        raise self._not_implemented("POST /v2/video/generate", DOCS)
