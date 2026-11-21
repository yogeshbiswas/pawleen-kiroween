"""SSE events: Pydantic models, encoding to text and parsing back.

Each event is framed as `event: <name>\\ndata: <json>\\n\\n`.
"""

import json
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel


class _Event(BaseModel):
    name: ClassVar[str]

    def to_sse(self):
        # Compact JSON has no raw newlines, so one `data:` line is enough.
        data = json.dumps(self.model_dump(), separators=(",", ":"))
        return f"event: {self.name}\ndata: {data}\n\n"


class StepEvent(_Event):
    name: ClassVar[str] = "step"
    step: Literal["gatekeeping", "brewing", "checking"]
    attempt: int = 1
    max_attempts: int = 2
    recast: bool = False


class HeartbeatEvent(_Event):
    name: ClassVar[str] = "heartbeat"
    t: int


class ResultEvent(_Event):
    name: ClassVar[str] = "result"
    image_b64: str
    mime: str = "image/png"
    costume_name: Optional[str] = None
    remaining: int
    limit: int
    notice: Optional[Literal["wonky", "not_verified"]] = None
    message: Optional[str] = None


class ErrorEvent(_Event):
    name: ClassVar[str] = "error"
    code: str
    message: str
    show_chips: bool = False
    retry_after_seconds: Optional[int] = None


EVENT_TYPES = {cls.name: cls for cls in (StepEvent, HeartbeatEvent, ResultEvent, ErrorEvent)}


def parse_sse(text):
    """Parse a buffer of SSE text into a list of event models.

    Blocks without a known event name or valid JSON data are skipped.
    """
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        cls = EVENT_TYPES.get(name)
        if cls is None or not data_lines:
            continue
        try:
            events.append(cls.model_validate(json.loads("\n".join(data_lines))))
        except ValueError:  # bad JSON or failed validation
            continue
    return events
