"""Anthropic: classifies a reply into one of the six categories.

Docs: https://docs.anthropic.com/en/api/messages

The model is forced to answer through a tool whose schema enumerates the six
categories, which is what stops it inventing a seventh or wrapping the answer in
prose. Anything it returns that is still not one of the six is treated as
UNCLEAR rather than trusted.
"""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import Category, Classification, Prospect, Reply

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = """\
You classify replies to a cold LinkedIn outreach message so that the sender can \
follow up with the right resource.

Choose UNCLEAR whenever you are not confident. A confident wrong answer sends \
the wrong material to a real person under the sender's name; UNCLEAR costs one \
human glance. Prefer UNCLEAR.

Report confidence honestly. Do not inflate it to seem decisive.\
"""

CLASSIFY_TOOL = {
    "name": "classify_reply",
    "description": "Record the classification of a single reply.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [c.value for c in Category],
                "description": (
                    "INTERESTED: positive, wants to know more. "
                    "BOOK_CALL: asking to meet or proposing a time. "
                    "OBJECTION: engaged but pushing back on price, timing or an incumbent. "
                    "NOT_INTERESTED: a clear no. "
                    "REFERRAL: pointing at a colleague. "
                    "UNCLEAR: anything you are not confident about."
                ),
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short phrases from the reply that drove the decision.",
            },
        },
        "required": ["category", "confidence", "signals"],
    },
}


class ClaudeClassifier(RealAdapter):
    ENV_KEY = "ANTHROPIC_API_KEY"
    EXTRA_ENV = {"ANTHROPIC_MODEL": "model"}

    def __init__(
        self,
        api_key: str,
        http=None,
        model: str = DEFAULT_MODEL,
        confidence_floor: float = 0.6,
        **options,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        self.model = model
        self.confidence_floor = confidence_floor

    def classify(self, reply: Reply, prospect: Prospect | None) -> Classification:
        try:
            payload = self.http.request(
                "POST",
                API_URL,
                headers={"x-api-key": self.api_key, "anthropic-version": API_VERSION},
                json_body={
                    "model": self.model,
                    "max_tokens": 512,
                    "system": SYSTEM,
                    "tools": [CLASSIFY_TOOL],
                    "tool_choice": {"type": "tool", "name": "classify_reply"},
                    "messages": [{"role": "user", "content": self._prompt(reply, prospect)}],
                },
            ).json()
        except Exception as exc:  # noqa: BLE001
            # An outage must not stop the run. An unclassified reply routes to
            # nothing and waits for a human, which is the safe failure.
            return Classification(Category.UNCLEAR, 0.0, (f"classifier unavailable: {exc}",))

        return self._apply_floor(self._parse(payload))

    @staticmethod
    def _prompt(reply: Reply, prospect: Prospect | None) -> str:
        who = (
            f"{prospect.name}, {prospect.role} at {prospect.company}"
            if prospect is not None
            else "an unknown contact"
        )
        return f"Prospect: {who}\n\nTheir reply:\n{reply.text}"

    @staticmethod
    def _parse(payload: dict) -> Classification:
        for block in payload.get("content", []):
            if block.get("type") != "tool_use":
                continue
            data = block.get("input") or {}
            raw = str(data.get("category", ""))
            if raw not in {c.value for c in Category}:
                # The schema says it cannot happen. If it does, do not guess.
                return Classification(Category.UNCLEAR, 0.0, ("model returned an unknown category",))
            return Classification(
                category=Category(raw),
                confidence=float(data.get("confidence", 0.0)),
                signals=tuple(str(s) for s in data.get("signals", [])),
            )
        return Classification(Category.UNCLEAR, 0.0, ("model did not use the tool",))

    def _apply_floor(self, classification: Classification) -> Classification:
        if classification.confidence < self.confidence_floor:
            return Classification(
                Category.UNCLEAR, classification.confidence, classification.signals
            )
        return classification
