from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import list_accounts, list_equity_snapshots
from db.models import Trade
from webapp.backend.schemas import DashboardSummaryOut, EquityPointOut

router = APIRouter(tags=["dashboard"])


def _closed_trades(db: Session, account_id: Optional[int] = None, since: Optional[datetime] = None):
    stmt = select(Trade).where(Trade.status == "closed")
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    if since is not None:
        stmt = stmt.where(Trade.closed_at >= since)
    return list(db.execute(stmt).scalars())


def _summarize(trades: list[Trade]) -> dict:
    total_pnl = sum(t.pnl or 0.0 for t in trades)
    n = len(trades)
    wins = sum(1 for t in trades if (t.pnl or 0.0) > 0)
    win_rate = round(wins / n * 100, 1) if n else 0.0
    return {"total_pnl": round(total_pnl, 2), "total_trades": n, "win_rate": win_rate}


@router.get("/api/dashboard/summary", response_model=DashboardSummaryOut)
def dashboard_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    all_trades = _closed_trades(db)
    weekly_trades = _closed_trades(db, since=now - timedelta(days=7))
    monthly_trades = _closed_trades(db, since=now - timedelta(days=30))

    overall = _summarize(all_trades)
    per_account = []
    for account in list_accounts(db):
        acc_trades = [t for t in all_trades if t.account_id == account.id]
        acc_summary = _summarize(acc_trades)
        per_account.append({
            "account_id": account.id, "broker": account.broker, "mode": account.mode,
            "label": account.label, **acc_summary,
        })

    return DashboardSummaryOut(
        total_pnl=overall["total_pnl"],
        total_trades=overall["total_trades"],
        weekly_pnl=round(sum(t.pnl or 0.0 for t in weekly_trades), 2),
        monthly_pnl=round(sum(t.pnl or 0.0 for t in monthly_trades), 2),
        win_rate=overall["win_rate"],
        per_account=per_account,
    )


@router.get("/api/equity", response_model=list[EquityPointOut])
def equity_curve(account_id: Optional[int] = None, db: Session = Depends(get_db)):
    return list_equity_snapshots(db, account_id=account_id)
