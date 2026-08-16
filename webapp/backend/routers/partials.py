"""
HTML fragments consumed by htmx polling on the dashboard. Reuses the same
DB helpers as the JSON API routers rather than duplicating query logic.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from db.base import get_db
from db.crud import list_signals
from webapp.backend.routers.dashboard import dashboard_summary
from webapp.backend.routers.health import health as health_check
from webapp.backend.templates import templates

router = APIRouter(prefix="/partials", tags=["partials"])


@router.get("/health")
def partial_health(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "partials/health_badge.html", {
        "health": health_check(db),
    })


@router.get("/summary")
def partial_summary(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "partials/summary_cards.html", {
        "summary": dashboard_summary(db),
    })


@router.get("/recent-signals")
def partial_recent_signals(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "partials/recent_signals.html", {
        "signals": list_signals(db, limit=15),
    })
