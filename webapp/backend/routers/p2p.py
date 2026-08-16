from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import add_p2p_transaction, list_p2p_transactions
from webapp.backend.schemas import P2PTransactionIn, P2PTransactionOut

router = APIRouter(prefix="/api/p2p", tags=["p2p"])


@router.get("", response_model=list[P2PTransactionOut])
def get_p2p(limit: int = 200, db: Session = Depends(get_db)):
    return list_p2p_transactions(db, limit=limit)


@router.post("", response_model=P2PTransactionOut)
def create_p2p(body: P2PTransactionIn, db: Session = Depends(get_db)):
    return add_p2p_transaction(db, **body.model_dump())
