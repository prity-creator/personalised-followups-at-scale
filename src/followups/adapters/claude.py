"""Anthropic: classifies a reply into one of the six categories."""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import Classification, Prospect, Reply

DOCS = "https://docs.anthropic.com/en/api/messages"

PROMPT = """\
You classify replies to a cold LinkedIn outreach message.

Return one of: INTERESTED, BOOK_CALL, OBJECTION, NOT_INTERESTED, REFERRAL, UNCLEAR.
Return UNCLEAR whenever you are not confident. Do not guess.

Also return a confidence between 0 and 1, and the short phrases in the reply
that drove your decision.

Prospect: {name}, {role} at {company}
Reply: {text}
"""


class ClaudeClassifier(RealAdapter):
    """Messages API with a strict output schema, then the same confidence floor.

    The floor rewrite is not duplicated here: it belongs to whichever classifier
    is in use and is applied identically to the mock, so a low confidence answer
    becomes UNCLEAR regardless of which one ran.
    """

    ENV_KEY = "ANTHROPIC_API_KEY"
    DEFAULT_MODEL = "claude-sonnet-5-5"

    def classify(self, reply: Reply, prospect: Prospect) -> Classification:
        raise self._not_implemented("POST /v1/messages", DOCS)
