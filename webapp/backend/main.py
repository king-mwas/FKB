"""
FastAPI app: dashboard, signals, trades, journal, screenshots, accounts,
P2P log, settings. Serves both the JSON API and the Jinja2/htmx frontend
from one process — see README for why (no Node build step needed).
"""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from db import crud
from db.base import get_db, init_db
from db.crud import list_accounts
from webapp.backend import auth
from webapp.backend.routers import (
    accounts, dashboard, health, journal, login, p2p, partials, screenshots,
    settings, signals, trades,
)
from webapp.backend.templates import templates

BASE_DIR = Path(__file__).resolve().parent.parent  # webapp/

auth.check_startup()

app = FastAPI(title="FKB")

# Order matters: middleware added last runs first, and require_login reads
# request.session, so SessionMiddleware must wrap it.
app.middleware("http")(auth.require_login)
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.secret_key(),
    same_site="lax",
    # Set FKB_COOKIE_INSECURE=true only to test over plain http on localhost.
    # Left on, the cookie is sent in clear over any non-TLS hop.
    https_only=os.environ.get("FKB_COOKIE_INSECURE", "false").lower() != "true",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "frontend" / "static")), name="static")

for router in (login.router, health.router, accounts.router, signals.router, trades.router,
               journal.router, screenshots.router, p2p.router, settings.router,
               dashboard.router, partials.router):
    app.include_router(router)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "dashboard.html", {
        "accounts": list_accounts(db),
    })


@app.get("/signals")
def signals_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "signals.html", {
        "signals": crud.list_signals(db, limit=200),
    })


@app.get("/trades")
def trades_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "trades.html", {
        "trades": crud.list_trades(db, limit=200),
    })


@app.get("/journal")
def journal_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "journal.html", {
        "entries": crud.list_journal_entries(db, limit=200),
    })


@app.get("/p2p")
def p2p_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "p2p.html", {
        "transactions": crud.list_p2p_transactions(db, limit=200),
    })
