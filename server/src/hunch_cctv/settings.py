from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    token: str | None
    default_threshold: float
    image_tokens: int
    max_body_bytes: int
    queue_size: int
    request_timeout: float
    state_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        threshold = float(os.getenv("HUNCH_THRESHOLD", "0.5"))
        if not 0.05 <= threshold <= 0.95:
            raise ValueError("HUNCH_THRESHOLD must be between 0.05 and 0.95")
        return cls(
            token=os.getenv("HUNCH_TOKEN") or None,
            default_threshold=threshold,
            image_tokens=int(os.getenv("HUNCH_IMAGE_TOKENS", "70")),
            max_body_bytes=int(os.getenv("HUNCH_MAX_BODY_BYTES", str(8 * 1024 * 1024))),
            queue_size=int(os.getenv("HUNCH_QUEUE_SIZE", "4")),
            request_timeout=float(os.getenv("HUNCH_REQUEST_TIMEOUT", "20")),
            state_dir=Path(os.getenv("HUNCH_STATE_DIR", "/data")),
        )

    def server_id(self) -> str:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / "server.json"
        try:
            return str(json.loads(path.read_text())["server_id"])
        except (FileNotFoundError, KeyError, ValueError, TypeError):
            value = str(uuid.uuid4())
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"server_id": value}))
            temporary.replace(path)
            return value
