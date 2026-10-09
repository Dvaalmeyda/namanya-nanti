"""Parser aliran peristiwa Server-Sent Events (SSE) dari endpoint streaming."""

from collections.abc import Generator
from dataclasses import dataclass
import json
from typing import Any


@dataclass
class SseEvent:
    """Representasi satu peristiwa Server-Sent Events (SSE)."""

    event: str
    data: dict[str, Any]


def parse_sse_stream(lines_iterator: Generator[str, None, None]) -> Generator[SseEvent, None, None]:
    """Mengurai aliran baris teks SSE menjadi objek SseEvent."""
    current_event = "message"
    current_data_lines: list[str] = []

    for raw_line in lines_iterator:
        line = raw_line.rstrip("\r\n")

        # Garis kosong menandai akhir dari satu paket event
        if not line:
            if current_data_lines:
                raw_data = "\n".join(current_data_lines)
                try:
                    payload = json.loads(raw_data)
                except Exception:
                    payload = {"raw": raw_data}

                yield SseEvent(event=current_event, data=payload)
                current_event = "message"
                current_data_lines = []
            continue

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line[len("data:"):].strip())

    # Proses event yang tersisa di akhir aliran
    if current_data_lines:
        raw_data = "\n".join(current_data_lines)
        try:
            payload = json.loads(raw_data)
        except Exception:
            payload = {"raw": raw_data}
        yield SseEvent(event=current_event, data=payload)
