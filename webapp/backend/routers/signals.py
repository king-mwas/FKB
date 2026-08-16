from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import list_signals
from db.models import Signal
from webapp.backend.schemas import SignalOut

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
def get_signals(account_id: Optional[int] = None, status: Optional[str] = None,
                 limit: int = 100, db: Session = Depends(get_db)):
    return list_signals(db, account_id=account_id, status=status, limit=limit)


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = db.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal
