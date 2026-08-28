"""Shared CRUD helpers used by both live_engine and webapp."""

from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import (
    Account, AppSetting, EquitySnapshot, JournalEntry, P2PTransaction,
    Screenshot, Signal, Trade,
)


def _native(fields: dict) -> dict:
    """Coerce numpy scalars to Python built-ins before they reach the driver.

    Detected zones come from pandas frames, so values like zone_top arrive as
    numpy.float64. SQLite accepts those (numpy.float64 subclasses float), but
    psycopg2 has no adapter for them and renders the repr into the SQL, which
    Postgres rejects with InvalidSchemaName: schema "np" does not exist. That
    makes every signal insert fail on Postgres while passing on the SQLite
    fallback, so normalise here at the persistence boundary rather than
    relying on each caller to remember."""
    out = {}
    for key, value in fields.items():
        if isinstance(value, np.generic):
            value = value.item()
        out[key] = value
    return out


# ---------------------------------------------------------------- accounts

def get_or_create_account(session: Session, broker: str, mode: str, label: str) -> Account:
    stmt = select(Account).where(Account.broker == broker, Account.mode == mode)
    account = session.execute(stmt).scalar_one_or_none()
    if account is None:
        account = Account(broker=broker, mode=mode, label=label)
        session.add(account)
        try:
            session.flush()
        except IntegrityError:
            # Another run inserted the same broker+mode between our select and
            # this flush. The unique constraint is what makes that a losable
            # race rather than a duplicate row, so take the winner's row.
            session.rollback()
            account = session.execute(stmt).scalar_one()
    return account


def list_accounts(session: Session) -> list[Account]:
    return list(session.execute(select(Account)).scalars())


def set_allocated_capital(session: Session, account_id: int, amount: float) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"No account with id={account_id}")
    account.allocated_capital = amount
    session.flush()
    return account


# ----------------------------------------------------------------- signals

def find_signal_by_fingerprint(session: Session, account_id: int, symbol: str,
                                ltf: str, variant: str, event_kind: str,
                                bar_time: datetime) -> Optional[Signal]:
    stmt = select(Signal).where(
        Signal.account_id == account_id, Signal.symbol == symbol,
        Signal.ltf == ltf, Signal.variant == variant,
        Signal.event_kind == event_kind, Signal.bar_time == bar_time,
    )
    return session.execute(stmt).scalar_one_or_none()


def create_signal(session: Session, **fields) -> Signal:
    signal = Signal(**_native(fields))
    session.add(signal)
    session.flush()
    return signal


def list_signals(session: Session, *, account_id: Optional[int] = None,
                  symbol: Optional[str] = None,
                  status: Optional[str] = None, limit: int = 100) -> list[Signal]:
    stmt = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
    if account_id is not None:
        stmt = stmt.where(Signal.account_id == account_id)
    if symbol is not None:
        stmt = stmt.where(Signal.symbol == symbol)
    if status is not None:
        stmt = stmt.where(Signal.status == status)
    return list(session.execute(stmt).scalars())


# ------------------------------------------------------------------ trades

def create_trade(session: Session, **fields) -> Trade:
    trade = Trade(**fields)
    session.add(trade)
    session.flush()
    return trade


def list_trades(session: Session, *, account_id: Optional[int] = None,
                 status: Optional[str] = None, limit: int = 100) -> list[Trade]:
    stmt = select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    if status is not None:
        stmt = stmt.where(Trade.status == status)
    return list(session.execute(stmt).scalars())


# ------------------------------------------------------------------ journal

def add_journal_entry(session: Session, *, trade_id: Optional[int], body: str,
                       title: Optional[str] = None, author: str = "owner",
                       tags: Optional[str] = None) -> JournalEntry:
    entry = JournalEntry(trade_id=trade_id, body=body, title=title,
                          author=author, tags=tags)
    session.add(entry)
    session.flush()
    return entry


def list_journal_entries(session: Session, limit: int = 100) -> list[JournalEntry]:
    stmt = select(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


# --------------------------------------------------------------- screenshots

def add_screenshot(session: Session, *, file_path: str,
                    trade_id: Optional[int] = None,
                    journal_entry_id: Optional[int] = None,
                    caption: Optional[str] = None) -> Screenshot:
    shot = Screenshot(file_path=file_path, trade_id=trade_id,
                       journal_entry_id=journal_entry_id, caption=caption)
    session.add(shot)
    session.flush()
    return shot


# -------------------------------------------------------------------- p2p

def add_p2p_transaction(session: Session, **fields) -> P2PTransaction:
    tx = P2PTransaction(**fields)
    session.add(tx)
    session.flush()
    return tx


def list_p2p_transactions(session: Session, limit: int = 200) -> list[P2PTransaction]:
    stmt = select(P2PTransaction).order_by(P2PTransaction.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


# ---------------------------------------------------------------- settings

def get_setting(session: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = session.get(AppSetting, key)
    return row.value if row else default


def set_setting(session: Session, key: str, value: str) -> AppSetting:
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.flush()
    return row


# ---------------------------------------------------------------- equity

def record_equity_snapshot(session: Session, *, account_id: int, equity: float,
                            balance: float, open_positions_count: int = 0) -> EquitySnapshot:
    snap = EquitySnapshot(account_id=account_id, equity=equity, balance=balance,
                           open_positions_count=open_positions_count)
    session.add(snap)
    session.flush()
    return snap


def list_equity_snapshots(session: Session, *, account_id: Optional[int] = None,
                           limit: int = 500) -> list[EquitySnapshot]:
    stmt = select(EquitySnapshot).order_by(EquitySnapshot.timestamp.asc()).limit(limit)
    if account_id is not None:
        stmt = stmt.where(EquitySnapshot.account_id == account_id)
    return list(session.execute(stmt).scalars())
