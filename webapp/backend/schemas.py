"""Pydantic request/response models for the FastAPI backend."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    broker: str
    mode: str
    label: str
    balance: float
    equity: float
    margin_used: float
    allocated_capital: float
    last_synced_at: Optional[datetime]


class AllocationIn(BaseModel):
    allocated_capital: float


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    account_id: int
    symbol: str
    ltf: str
    htf: str
    track: str
    variant: str
    event_kind: str
    direction: int
    bar_time: datetime
    htf_bias: int
    session_ok: bool
    zone_type: str
    zone_top: float
    zone_bottom: float
    sweep_confirmed: bool
    status: str
    confidence_score: Optional[int]
    confidence_reasoning: Optional[str]
    confidence_concerns: Optional[str]
    confidence_error: Optional[str]
    trade_id: Optional[int]


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    signal_id: Optional[int]
    symbol: str
    direction: int
    entry_price: float
    sl: Optional[float]
    tp: Optional[float]
    lots_or_qty: float
    opened_at: datetime
    closed_at: Optional[datetime]
    exit_price: Optional[float]
    pnl: Optional[float]
    r_multiple: Optional[float]
    broker_order_id: Optional[str]
    status: str
    risk_amount: Optional[float]
    equity_at_entry: Optional[float]
    equity_at_exit: Optional[float]


class JournalEntryIn(BaseModel):
    trade_id: Optional[int] = None
    title: Optional[str] = None
    body: str
    tags: Optional[str] = None


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trade_id: Optional[int]
    created_at: datetime
    author: str
    title: Optional[str]
    body: str
    tags: Optional[str]


class ScreenshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trade_id: Optional[int]
    journal_entry_id: Optional[int]
    created_at: datetime
    file_path: str
    caption: Optional[str]


class P2PTransactionIn(BaseModel):
    counterparty_name: str
    contact: Optional[str] = None
    type: str  # "deposit" | "withdrawal"
    currency: str
    amount: float
    rate: Optional[float] = None
    linked_account_id: Optional[int] = None
    status: str = "pending"
    notes: Optional[str] = None


class P2PTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    counterparty_name: str
    contact: Optional[str]
    type: str
    currency: str
    amount: float
    rate: Optional[float]
    linked_account_id: Optional[int]
    status: str
    notes: Optional[str]


class EquityPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    timestamp: datetime
    account_id: int
    equity: float
    balance: float


class DashboardSummaryOut(BaseModel):
    total_pnl: float
    total_trades: int
    weekly_pnl: float
    monthly_pnl: float
    win_rate: float
    per_account: list[dict]


class SettingIn(BaseModel):
    key: str
    value: str


class HealthOut(BaseModel):
    status: str
    db_ok: bool
    engines: list[dict]
