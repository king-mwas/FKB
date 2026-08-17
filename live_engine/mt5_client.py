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


def current_price(symbol: str, direction: int) -> float:
    """Current tradeable price for a slippage check -- ask for a long
    entry, bid for a short entry (the side we'd actually transact at)."""
    ensure_connected()
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"symbol_info_tick failed for {symbol}: {mt5.last_error()}")
    return tick.ask if direction == 1 else tick.bid


def place_market_order(symbol: str, direction: int, lots: float, sl: float, tp: float,
                        deviation: int, comment: str) -> dict:
    """Sends a market order (TRADE_ACTION_DEAL). Raises RuntimeError on any
    non-DONE retcode -- order placement must fail closed like every other
    broker call in this module. `deviation` is in MT5 points, not pips --
    a broker's point size can differ from fkb_strategy.config's AccountSpec
    pip (5-digit vs 4-digit quoting); verify against your broker before
    live use."""
    ensure_connected()
    order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": comment,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        raise RuntimeError(f"order_send failed for {symbol}: retcode={code}")
    return {"ticket": result.order, "price": result.price}


def get_position(ticket: int):
    ensure_connected()
    positions = mt5.positions_get(ticket=ticket)
    return positions[0] if positions else None


def get_closed_deal(ticket: int):
    """Looks up the closing deal for a position ticket once it's no longer
    open -- gives the exit price/profit MT5 actually filled at."""
    ensure_connected()
    deals = mt5.history_deals_get(position=ticket)
    if not deals:
        return None
    closing = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    return closing[-1] if closing else None
