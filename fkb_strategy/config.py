"""
Shared account/symbol configuration for the FKB SMC strategy.

Used by both the offline backtester and the live engine — this is the
single source of truth for symbol specs, timeframe mapping, and account
sizing rules. Edit here, not in individual scripts.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountSpec:
    """Per-symbol trading spec: pip size, typical spread, contract size."""
    pip: float
    spread_pips: float
    contract: float


# Your broker's symbol names. Check exactly how they appear in MT5 Market
# Watch — many brokers suffix symbols, e.g. "EURUSD." or "XAUUSD.".
SYMBOLS = {
    "XAUUSD": AccountSpec(pip=0.10, spread_pips=25, contract=100),
    "EURUSD": AccountSpec(pip=0.0001, spread_pips=1.5, contract=100_000),
    "USDJPY": AccountSpec(pip=0.01, spread_pips=1.5, contract=100_000),
}

# Binance spot symbols tracked live (see fkb_strategy/data_binance.py).
# PAXGUSDT is Paxos Gold -- one token is one fine troy ounce, so it tracks
# spot gold and is the closest thing to a metals instrument available here.
# There is no comparable silver market on Binance, so XAGUSD stays an MT5-only
# symbol until the Windows side is running.
BINANCE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "PAXGUSDT"]

TF_MAP = {
    "M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

# Binance kline interval strings, mirroring TF_MAP's keys.
BINANCE_TF_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
}

STARTING_BALANCE = 30.0
RISK_PER_TRADE_PCT = 2.0
MAX_CONCURRENT = 1
COMMISSION_PER_LOT = 0.0

# Cent account: 1 lot = 1,000 units, so P&L is 1/100th of a standard account.
CENT_ACCOUNT = True

MIN_LOT = 0.01
LOT_STEP = 0.01
MAX_LOT = 200.0 if CENT_ACCOUNT else 50.0
