from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import list_trades
from db.models import Trade
from webapp.backend.schemas import JournalEntryOut, ScreenshotOut, TradeOut

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeOut])
def get_trades(account_id: Optional[int] = None, status: Optional[str] = None,
                limit: int = 100, db: Session = Depends(get_db)):
    return list_trades(db, account_id=account_id, status=status, limit=limit)


@router.get("/{trade_id}")
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {
        "trade": TradeOut.model_validate(trade),
        "journal_entries": [JournalEntryOut.model_validate(j) for j in trade.journal_entries],
        "screenshots": [ScreenshotOut.model_validate(s) for s in trade.screenshots],
    }
