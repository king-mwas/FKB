from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import set_setting
from db.models import AppSetting
from webapp.backend.schemas import SettingIn

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Defense in depth: these stay .env-only (see db/models.py AppSetting
# docstring). Even if the frontend never sends them, reject them here too
# so a stray click can never flip an account to live trading.
FORBIDDEN_KEY_SUBSTRINGS = ("MODE", "ALLOW_LIVE", "API_KEY", "SECRET", "PASSWORD")


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    rows = db.execute(select(AppSetting)).scalars()
    return {row.key: row.value for row in rows}


@router.post("")
def update_setting(body: SettingIn, db: Session = Depends(get_db)):
    key_upper = body.key.upper()
    if any(bad in key_upper for bad in FORBIDDEN_KEY_SUBSTRINGS):
        raise HTTPException(
            status_code=400,
            detail=f"'{body.key}' must be set via .env, not the web UI.",
        )
    row = set_setting(db, body.key, body.value)
    return {row.key: row.value}
