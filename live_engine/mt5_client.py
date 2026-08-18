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


def last_error():
    return mt5.last_error()


def _clamp_volume(symbol: str, lots: float) -> float:
    """Round/clamp our computed lot size to this symbol's actual broker
    constraints (volume_min/step/max) -- our own MIN_LOT/LOT_STEP/MAX_LOT
    config is a best guess and the real symbol_info is authoritative."""
    info = mt5.symbol_info(symbol)
    if info is None or not info.volume_step:
        return lots
    lots = max(info.volume_min, min(info.volume_max, lots))
    steps = round(lots / info.volume_step)
    return round(steps * info.volume_step, 8)


def _filling_type(symbol_info) -> int:
    mode = symbol_info.filling_mode
    if mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def place_market_order(symbol: str, direction: int, lots: float, sl: float, tp: float,
                        *, deviation: int, magic: int, comment: str):
    """Send a market order with SL/TP attached. Returns the raw mt5
    OrderSendResult (or None on a transport-level failure) -- the caller
    inspects .retcode itself; a broker-side rejection is a normal outcome
    to log, not something this function raises on."""
    ensure_connected()
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"symbol_select({symbol}) failed: {mt5.last_error()}")

    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol}) failed: {mt5.last_error()}")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"symbol_info_tick({symbol}) failed: {mt5.last_error()}")

    order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == 1 else tick.bid
    digits = info.digits
    volume = _clamp_volume(symbol, lots)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": round(price, digits),
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "deviation": deviation,
        "magic": magic,
        "comment": comment[:31],  # MT5 truncates/rejects longer comments
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_type(info),
    }
    return mt5.order_send(request)
