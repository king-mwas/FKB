from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import add_journal_entry, list_journal_entries
from webapp.backend.schemas import JournalEntryIn, JournalEntryOut

router = APIRouter(tags=["journal"])


@router.get("/api/journal", response_model=list[JournalEntryOut])
def get_journal(limit: int = 100, db: Session = Depends(get_db)):
    return list_journal_entries(db, limit=limit)


@router.post("/api/trades/{trade_id}/journal", response_model=JournalEntryOut)
def add_trade_journal_entry(trade_id: int, body: JournalEntryIn, db: Session = Depends(get_db)):
    entry = add_journal_entry(db, trade_id=trade_id, body=body.body,
                               title=body.title, tags=body.tags)
    return entry
