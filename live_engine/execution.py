"""
MT5 order execution for confidence-passed signals (Phase 5/6).

Reuses the same PendingSetup/build_trade_plan/position_size math the
backtester and confidence preview already use, so the live-executed trade
can never silently drift from what was backtested or previewed to Claude.

Safety: two independent gates must both hold before any order reaches a
*live* account -- MT5_MODE=="live" AND ALLOW_LIVE_TRADING==True (see
live_engine/config.py / README). If MT5_MODE=="live" but the guard is off,
this module refuses to trade even though mt5_client already connected to
the live account for data purposes -- a single misconfigured var can't
accidentally trade real money. Every order attempt -- success or broker
rejection -- is logged and written back onto the Signal; nothing here
raises out to the caller, matching confidence.py's fail-closed style.

Binance execution is out of scope here (Phase 8) -- caller should only
invoke try_execute() for account.broker == "mt5".
"""

from typing import Optional

from db.crud import create_trade
from db.models import Account, Signal
from fkb_strategy.config import (
    CENT_ACCOUNT, LOT_STEP, MAX_LOT, MIN_LOT, RISK_PER_TRADE_PCT, SYMBOLS,
)
from fkb_strategy.setups import PendingSetup, TradePlan, build_trade_plan
from fkb_strategy.sizing import position_size
from live_engine import config, mt5_client


def build_live_trade_plan(signal: Signal) -> Optional[TradePlan]:
    """Rebuild the same trade plan confidence.py previewed to Claude, from
    the signal's recorded zone. Returns None if the symbol has no
    AccountSpec yet (Binance -- Phase 8) or the stop distance is a
    micro-stop (build_trade_plan's own noise guard)."""
    spec = SYMBOLS.get(signal.symbol)
    if spec is None:
        return None
    pending = PendingSetup(
        variant=signal.variant, kind=signal.event_kind, direction=signal.direction,
        zone_type=signal.zone_type, top=signal.zone_top, bottom=signal.zone_bottom,
        armed_at=0,
    )
    spread = spec.spread_pips * spec.pip
    return build_trade_plan(pending, spread=spread, rr=config.DEFAULT_RR, pip=spec.pip)


def _fail(session, signal: Signal, status: str, message: str) -> None:
    signal.status = status
    signal.confidence_error = message
    session.flush()
    print(f"    -> execution: {message}")


def try_execute(session, signal: Signal, account: Account) -> None:
    """Attempt to execute a confidence_pass MT5 signal in place. Mutates
    signal.status to filled/skipped_max_concurrent/skipped_error; creates a
    Trade row on success. Only call when signal.status == 'confidence_pass'
    and account.broker == 'mt5'."""
    plan = build_live_trade_plan(signal)
    if plan is None:
        _fail(session, signal, "skipped_error",
              "execution: no trade plan (missing symbol spec or micro-stop)")
        return

    open_count = mt5_client.open_positions_count(signal.symbol)
    if open_count >= config.MAX_CONCURRENT_PER_SYMBOL:
        _fail(session, signal, "skipped_max_concurrent",
              f"execution: {open_count} open position(s) already on {signal.symbol} "
              f"(max {config.MAX_CONCURRENT_PER_SYMBOL})")
        return

    if config.MT5_MODE == "live" and not config.ALLOW_LIVE_TRADING:
        _fail(session, signal, "skipped_error",
              "execution: MT5_MODE=live but ALLOW_LIVE_TRADING is not true -- refusing to trade")
        return

    spec = SYMBOLS[signal.symbol]
    lots = position_size(
        account.equity, RISK_PER_TRADE_PCT, plan.stop_distance, spec,
        cent_account=CENT_ACCOUNT, min_lot=MIN_LOT, lot_step=LOT_STEP, max_lot=MAX_LOT,
    )
    if lots <= 0:
        _fail(session, signal, "skipped_error",
              "execution: broker minimum lot exceeds risk budget at current equity")
        return

    comment = f"FKB {signal.variant}"[:31]
    try:
        result = mt5_client.place_market_order(
            signal.symbol, signal.direction, lots, plan.sl, plan.tp,
            deviation=config.ORDER_DEVIATION_POINTS, magic=config.EXECUTION_MAGIC,
            comment=comment,
        )
    except RuntimeError as e:
        _fail(session, signal, "skipped_error", f"execution: {e}")
        return

    if result is None:
        _fail(session, signal, "skipped_error",
              f"execution: order_send returned None: {mt5_client.last_error()}")
        return

    print(f"    -> execution request: {signal.symbol} dir={signal.direction:+d} "
          f"lots={lots} sl={plan.sl:.5f} tp={plan.tp:.5f} mode={config.MT5_MODE} "
          f"-> retcode={result.retcode} comment={result.comment!r}")

    if result.retcode != mt5_client.mt5.TRADE_RETCODE_DONE:
        _fail(session, signal, "skipped_error",
              f"execution: broker rejected order, retcode={result.retcode} ({result.comment})")
        return

    trade = create_trade(
        session, account_id=account.id, signal_id=signal.id, symbol=signal.symbol,
        direction=signal.direction, entry_price=result.price, sl=plan.sl, tp=plan.tp,
        lots_or_qty=lots, broker_order_id=str(result.order), status="open",
        risk_amount=account.equity * (RISK_PER_TRADE_PCT / 100.0),
        equity_at_entry=account.equity,
    )
    signal.status = "filled"
    signal.trade_id = trade.id
    session.flush()
    print(f"    -> FILLED: trade_id={trade.id} order_id={result.order} entry={result.price:.5f}")
