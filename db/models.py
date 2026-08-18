"""
Shared DB schema — single source of truth for both live_engine and webapp.
Postgres (Supabase) -- see db/base.py.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Account(Base):
    """One row per broker account we trade/observe: MT5 demo, MT5 live,
    Binance testnet, Binance live, etc."""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker: Mapped[str] = mapped_column(String(16))          # "mt5" | "binance"
    mode: Mapped[str] = mapped_column(String(16))            # "demo"|"live" or "testnet"|"live"
    label: Mapped[str] = mapped_column(String(64))
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    margin_used: Mapped[float] = mapped_column(Float, default=0.0)
    # Owner-editable cap on how much capital this account's sizing may use —
    # the "increase/decrease margin" control from the dashboard.
    allocated_capital: Mapped[float] = mapped_column(Float, default=0.0)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    trades: Mapped[list["Trade"]] = relationship(back_populates="account")
    signals: Mapped[list["Signal"]] = relationship(back_populates="account")


class Signal(Base):
    """Every detected structural event, whether or not it traded."""
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "ltf", "variant", "event_kind", "bar_time",
                          name="uq_signal_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    ltf: Mapped[str] = mapped_column(String(8))
    htf: Mapped[str] = mapped_column(String(8))
    track: Mapped[str] = mapped_column(String(32))
    variant: Mapped[str] = mapped_column(String(32))
    event_kind: Mapped[str] = mapped_column(String(8))        # "BOS" | "CHOCH"
    direction: Mapped[int] = mapped_column(Integer)            # 1 | -1
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    htf_bias: Mapped[int] = mapped_column(Integer, default=0)
    session_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    zone_type: Mapped[str] = mapped_column(String(8))          # "OB" | "FVG"
    zone_top: Mapped[float] = mapped_column(Float)
    zone_bottom: Mapped[float] = mapped_column(Float)
    sweep_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # detected/confidence_pass/skipped_confidence/skipped_error/
    # skipped_rate_limited/filled/expired/skipped_max_concurrent
    status: Mapped[str] = mapped_column(String(32), default="detected")

    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_concerns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list
    confidence_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="signals")
    trade: Mapped[Optional["Trade"]] = relationship(back_populates="signal", foreign_keys=[trade_id])


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("signals.id"), nullable=True)

    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    sl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lots_or_qty: Mapped[float] = mapped_column(Float)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open/closed/cancelled
    risk_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity_at_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity_at_exit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="trades")
    signal: Mapped[Optional["Signal"]] = relationship(back_populates="trade", foreign_keys=[Signal.trade_id])
    journal_entries: Mapped[list["JournalEntry"]] = relationship(back_populates="trade")
    screenshots: Mapped[list["Screenshot"]] = relationship(
        back_populates="trade", foreign_keys="Screenshot.trade_id")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    author: Mapped[str] = mapped_column(String(64), default="owner")
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # comma-separated

    trade: Mapped[Optional["Trade"]] = relationship(back_populates="journal_entries")
    screenshots: Mapped[list["Screenshot"]] = relationship(
        back_populates="journal_entry", foreign_keys="Screenshot.journal_entry_id")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"), nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    file_path: Mapped[str] = mapped_column(String(500))
    caption: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    trade: Mapped[Optional["Trade"]] = relationship(back_populates="screenshots", foreign_keys=[trade_id])
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship(
        back_populates="screenshots", foreign_keys=[journal_entry_id])


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    equity: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)


class P2PTransaction(Base):
    """Record-keeping only — logs P2P deposits/withdrawals the owner
    personally facilitates as a Binance P2P agent. Does not move money."""
    __tablename__ = "p2p_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    counterparty_name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(16))               # "deposit" | "withdrawal"
    currency: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Float)
    rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    linked_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/completed/cancelled
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    """Key/value settings editable from the web UI. Deliberately excludes
    MT5_MODE / ALLOW_LIVE_TRADING / BINANCE_MODE / ALLOW_LIVE_BINANCE_TRADING
    — those stay .env-only so a stray click can never flip an account live."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
