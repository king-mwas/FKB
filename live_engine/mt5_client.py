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


def _clamp_volume(symbol_info, lots: float) -> float:
    """Round/clamp our computed lot size to this symbol's actual broker
    constraints (volume_min/step/max) -- our own MIN_LOT/LOT_STEP/MAX_LOT
    config is a best guess and the real symbol_info is authoritative."""
    if not symbol_info.volume_step:
        return lots
    lots = max(symbol_info.volume_min, min(symbol_info.volume_max, lots))
    steps = round(lots / symbol_info.volume_step)
    return round(steps * symbol_info.volume_step, 8)


def _filling_type(symbol_info) -> int:
    """Pick the fill mode from what this symbol actually supports rather
    than assuming one -- brokers vary in which of FOK/IOC/RETURN they
    allow, and requesting an unsupported mode gets the whole order
    rejected."""
    mode = symbol_info.filling_mode
    if mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def place_market_order(symbol: str, direction: int, lots: float, sl: float, tp: float,
                        deviation: int, magic: int, comment: str) -> dict:
    """Sends a market order (TRADE_ACTION_DEAL). Raises RuntimeError on any
    failure -- symbol lookup, or a non-DONE retcode -- order placement must
    fail closed like every other broker call in this module. `deviation` is
    in MT5 points (see live_engine/config.py's ORDER_DEVIATION_POINTS).
    Volume is clamped to the symbol's real volume_min/step/max and the fill
    mode is read from what the symbol actually supports, since both vary
    by broker and our own config is only a best guess."""
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
    volume = _clamp_volume(info, lots)

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
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        detail = f" ({result.comment})" if result else ""
        raise RuntimeError(f"order_send failed for {symbol}: retcode={code}{detail}")
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
