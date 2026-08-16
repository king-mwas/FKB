"""
MT5 connection management for the live engine. Distinct from
fkb_strategy/data_mt5.py's load()/load_recent() (which assume *some*
account is already logged into the terminal) — this module explicitly logs
into the account configured for MT5_MODE (demo/live) via .env, so the
engine always knows which account it's actually trading, rather than
trusting whatever the terminal happened to be logged into.

Operational note (see the plan): MT5's Python API is a single terminal
session — this connect() call wins terminal-wide over any concurrent
interactive MCP inspection against a different account.
"""

import MetaTrader5 as mt5

from live_engine import config


def connect() -> bool:
    """Log into the configured MT5_MODE account. Falls back to whatever
    account the terminal is already logged into if no credentials are
    configured in .env (useful for early testing before HFM demo creds
    are set up)."""
    if config.MT5_LOGIN and config.MT5_PASSWORD and config.MT5_SERVER:
        ok = mt5.initialize(login=int(config.MT5_LOGIN),
                             password=config.MT5_PASSWORD,
                             server=config.MT5_SERVER)
    else:
        ok = mt5.initialize()
    return ok


def ensure_connected():
    if not connect():
        raise RuntimeError(f"MT5 connect failed: {mt5.last_error()}")


def account_summary() -> dict:
    ensure_connected()
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"account_info() failed: {mt5.last_error()}")
    return {
        "login": info.login, "server": info.server, "balance": info.balance,
        "equity": info.equity, "margin": info.margin,
        "margin_free": info.margin_free,
    }


def open_positions_count(symbol: str = None) -> int:
    ensure_connected()
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return len(positions) if positions else 0
