"""Stable uploads location shared by releases; local default is for development."""

import os
from pathlib import Path

from app.core.config import BACKEND_DIR


def uploads_root() -> Path:
    configured = os.environ.get("HASHTI_UPLOADS_DIR")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise RuntimeError("HASHTI_UPLOADS_DIR must be an absolute path")
        return path
    return BACKEND_DIR.parent / ".local" / "uploads"
