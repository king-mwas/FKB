"""Screenshot upload handling: validate, save to disk, return a relative path."""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

SCREENSHOTS_DIR = Path(os.environ.get("FKB_SCREENSHOTS_DIR", "./data/screenshots"))
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_BYTES = 15 * 1024 * 1024  # 15 MB


async def save_upload(file: UploadFile) -> str:
    """Saves the uploaded file under SCREENSHOTS_DIR with a random name,
    preserving its extension. Returns the path relative to SCREENSHOTS_DIR.
    Raises ValueError on an unsupported extension or oversized file."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    dest = SCREENSHOTS_DIR / name

    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"File exceeds {MAX_BYTES // (1024 * 1024)}MB limit")
            out.write(chunk)

    return name
