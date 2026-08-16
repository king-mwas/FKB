from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import add_screenshot
from db.models import Screenshot
from webapp.backend.schemas import ScreenshotOut
from webapp.backend.services.screenshot_service import SCREENSHOTS_DIR, save_upload

router = APIRouter(tags=["screenshots"])


@router.post("/api/screenshots", response_model=ScreenshotOut)
async def upload_screenshot(
    file: UploadFile = File(...),
    trade_id: Optional[int] = Form(None),
    journal_entry_id: Optional[int] = Form(None),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        rel_path = await save_upload(file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return add_screenshot(db, file_path=rel_path, trade_id=trade_id,
                           journal_entry_id=journal_entry_id, caption=caption)


@router.get("/screenshots/{screenshot_id}/file")
def get_screenshot_file(screenshot_id: int, db: Session = Depends(get_db)):
    shot = db.get(Screenshot, screenshot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    path = Path(SCREENSHOTS_DIR) / shot.file_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path)
