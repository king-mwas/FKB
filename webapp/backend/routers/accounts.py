from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import list_accounts, set_allocated_capital
from webapp.backend.schemas import AccountOut, AllocationIn

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def get_accounts(db: Session = Depends(get_db)):
    return list_accounts(db)


@router.post("/{account_id}/allocation", response_model=AccountOut)
def update_allocation(account_id: int, body: AllocationIn, db: Session = Depends(get_db)):
    try:
        return set_allocated_capital(db, account_id, body.allocated_capital)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
