import pytest

from app.core.config import BACKEND_DIR
from app.core.storage import uploads_root


def test_uploads_root_defaults_to_local_project_path(monkeypatch):
    monkeypatch.delenv("HASHTI_UPLOADS_DIR", raising=False)
    assert uploads_root() == BACKEND_DIR.parent / ".local" / "uploads"


def test_uploads_root_accepts_shared_absolute_path(monkeypatch, tmp_path):
    shared = tmp_path / "shared-uploads"
    monkeypatch.setenv("HASHTI_UPLOADS_DIR", str(shared))
    assert uploads_root() == shared


def test_uploads_root_rejects_relative_path(monkeypatch):
    monkeypatch.setenv("HASHTI_UPLOADS_DIR", "uploads")
    with pytest.raises(RuntimeError, match="absolute path"):
        uploads_root()
