from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db.base import get_db
from db.models import AppSetting
from webapp.backend.schemas import HealthOut

router = APIRouter(prefix="/api/health", tags=["health"])

HEARTBEAT_PREFIX = "engine_heartbeat:"


@router.get("", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # The live engine writes an "engine_heartbeat:<broker>:<track>" setting
    # on every poll — one row per running track.
    stmt = select(AppSetting).where(AppSetting.key.like(f"{HEARTBEAT_PREFIX}%"))
    engines = [
        {"track": row.key[len(HEARTBEAT_PREFIX):], "last_poll": row.value}
        for row in db.execute(stmt).scalars()
    ]

    return HealthOut(status="ok" if db_ok else "degraded", db_ok=db_ok, engines=engines)
