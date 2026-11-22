from __future__ import annotations

import base64
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def default_dataset_directory() -> Path:
    data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    ).expanduser()
    return data_home / "local-green-man-assistant" / "dataset"


class DatasetRecorder:
    """Thread-safe recorder for approved (screenshot, prompt, tool_call) examples."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_dataset_directory()
        self.images_dir = self.directory / "images"
        self.jsonl_path = self.directory / "approved_actions.jsonl"
        self._lock = threading.Lock()

    def record(
        self,
        *,
        source: str,
        model: str,
        prompt: str,
        tool_name: str,
        tool_arguments: dict,
        screenshot_b64: str | None = None,
        screenshot_size: tuple[int, int] | None = None,
        system_prompt: str | None = None,
    ) -> Path:
        timestamp = datetime.now(timezone.utc)
        image_rel_path: str | None = None

        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            if screenshot_b64:
                image_bytes = base64.b64decode(screenshot_b64, validate=True)
                ext = ".png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
                filename = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}{ext}"
                self.images_dir.mkdir(parents=True, exist_ok=True)
                (self.images_dir / filename).write_bytes(image_bytes)
                image_rel_path = f"images/{filename}"

            entry = {
                "timestamp": timestamp.isoformat(),
                "source": source,
                "model": model,
                "prompt": prompt,
                "screenshot": image_rel_path,
                "screenshot_size": list(screenshot_size) if screenshot_size else None,
                "tool_call": {
                    "name": tool_name,
                    "arguments": tool_arguments,
                },
            }
            if system_prompt is not None:
                entry["system_prompt"] = system_prompt

            with self.jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return self.jsonl_path
