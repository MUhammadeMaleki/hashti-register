"""Shared limits and preview authorization for Excel imports."""

import hashlib
import hmac
import time
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook

from app.core.config import Settings
from app.services.auth import Actor

MAX_FILE_BYTES = 3 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_ROWS = 5000


async def read_xlsx(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "invalid_import_file")
    return await file.read(MAX_FILE_BYTES + 1)


def checked_workbook(content: bytes):
    if not content or len(content) > MAX_FILE_BYTES:
        raise HTTPException(422, "invalid_import_size")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 100 or sum(
                entry.file_size for entry in archive.infolist()
            ) > MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(422, "invalid_import_size")
        return load_workbook(BytesIO(content), read_only=True, data_only=False)
    except (BadZipFile, OSError, ValueError, KeyError):
        raise HTTPException(422, "invalid_import_file") from None


def preview_token(content: bytes, actor: Actor, settings: Settings, expiry: int) -> str:
    digest = hashlib.sha256(content).hexdigest()
    message = f"{actor.id}:{digest}:{expiry}"
    signature = hmac.new(settings.auth_secret.get_secret_value().encode(),
                         message.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}:{signature}"


def verify_preview_token(token: str, content: bytes, actor: Actor, settings: Settings) -> None:
    try:
        expiry = int(token.split(":", 1)[0])
    except ValueError:
        raise HTTPException(422, "invalid_import_preview") from None
    if expiry < time.time() or not hmac.compare_digest(
        token, preview_token(content, actor, settings, expiry)
    ):
        raise HTTPException(422, "invalid_import_preview")
