"""Tiny local state file so repeated calls reuse one Flow project."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

STATE_PATH = Path(os.environ.get("SELFFLOW_STATE", str(Path.home() / ".selfflow" / "state.json")))


def load_project_id() -> Optional[str]:
    try:
        data = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return None
    value = data.get("project_id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def save_project_id(project_id: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"project_id": project_id}, indent=2) + "\n")
