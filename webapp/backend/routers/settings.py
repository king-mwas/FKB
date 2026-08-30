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
FORBIDDEN_KEY_SUBSTRINGS = ("MODE", "ALLOW_LIVE", "API_KEY", "SECRET",
                            "PASSWORD", "TOKEN")

REDACTED = "<redacted>"


def _is_sensitive(key: str) -> bool:
    key_upper = key.upper()
    return any(bad in key_upper for bad in FORBIDDEN_KEY_SUBSTRINGS)


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """Values for sensitive keys are redacted, not omitted -- the caller can
    still confirm a key is set without the endpoint handing out its value.
    app_settings now holds ANTHROPIC_API_KEY (see live_engine/confidence.py),
    so returning rows verbatim would publish a live credential to anyone who
    can reach this route -- and nothing in this app authenticates."""
    rows = db.execute(select(AppSetting)).scalars()
    return {row.key: (REDACTED if _is_sensitive(row.key) else row.value)
            for row in rows}


@router.post("")
def update_setting(body: SettingIn, db: Session = Depends(get_db)):
    if _is_sensitive(body.key):
        raise HTTPException(
            status_code=400,
            detail=f"'{body.key}' must be set via .env, not the web UI.",
        )
    row = set_setting(db, body.key, body.value)
    return {row.key: row.value}
