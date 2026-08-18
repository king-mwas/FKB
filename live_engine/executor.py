"""
Order execution (Phase 5): turns a confidence_pass Signal into a real MT5
trade once its zone is actually touched, then keeps that Trade's status in
sync with the broker until it closes.

Reuses fkb_strategy.setups.check_fill()/build_trade_plan() and
fkb_strategy.sizing.position_size() verbatim -- the same functions the
backtester uses -- so live execution can never silently drift from what was
backtested. MT5 only; Binance execution is out of scope here (see
live_engine/config.py's TRACKS comment -- Binance tracks stay inert until a
Binance executor is built).

Fill mechanism: poll-driven re-check of check_fill() against freshly
fetched candles (same stateless-recompute pattern as detector.py), not a
resting broker-side pending order -- keeps live fill logic identical to
what smc_backtest.py already measured. When a touch fires, this places a
MARKET order with a slippage guard (skip, fail closed, if price has moved
too far from the planned entry) rather than a resting limit order at the
exact zone price, since a resting order needs its own broker-side
lifecycle tracking that hasn't been built or verified here.
"""

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from db.crud import create_trade, list_signals, list_trades, record_equity_snapshot
from db.models import Account, Signal
from fkb_strategy.config import (
    CENT_ACCOUNT, LOT_STEP, MAX_LOT, MIN_LOT, RISK_PER_TRADE_PCT, SYMBOLS,
)
from fkb_strategy.setups import PendingSetup, build_trade_plan, check_fill
from fkb_strategy.sizing import position_size
from live_engine import config, mt5_client

# How far price may have moved from the planned entry (in stop-distance
# multiples) before a touched setup is skipped instead of chased at a
# worse price. Fail closed on bad fills, same as confidence.py fails
# closed on bad scores.
MAX_SLIPPAGE_STOP_FRACTION = 0.25


def _pending_from_signal(signal: Signal, armed_at: int) -> PendingSetup:
    return PendingSetup(
        variant=signal.variant, kind=signal.event_kind, direction=signal.direction,
        zone_type=signal.zone_type, top=signal.zone_top, bottom=signal.zone_bottom,
        armed_at=armed_at,
    )


def _open_or_pending_count(session: Session, account_id: int, symbol: str) -> int:
    trades = list_trades(session, account_id=account_id, status="open", limit=500)
    return sum(1 for t in trades if t.symbol == symbol)


def _live_guard_ok(mode: str) -> bool:
    """mode=="demo"/"testnet" trades freely (not real money). mode=="live"
    ALSO needs ALLOW_LIVE_TRADING -- the two-guard design .env.example
    already documents; this is the one place that guard is enforced before
    an order can reach the broker."""
    if mode != "live":
        return True
    return config.ALLOW_LIVE_TRADING


def check_fills_and_execute(session: Session, account: Account, track: dict,
                             symbol: str, ltf_df: pd.DataFrame) -> None:
    """For every confidence_pass Signal on this (account, track, symbol),
    re-run check_fill() against the freshly fetched candle window. Touched
    -> execute; expired -> mark expired; neither -> left as-is for the next
    poll to re-check."""
    pending = [
        s for s in list_signals(session, account_id=account.id, symbol=symbol,
                                 status="confidence_pass", limit=200)
        if s.track == track["name"] and s.ltf == track["ltf"]
    ]

    for signal in pending:
        armed_idx = ltf_df.index.get_indexer([signal.bar_time])[0]
        if armed_idx == -1:
            # Arming bar has rolled out of the rolling window -- too much
            # time has passed to still act on it. Fail closed: expire.
            signal.status = "expired"
            session.flush()
            continue

        setup = _pending_from_signal(signal, armed_idx)

        outcome = None  # "touched" | "expired" | None (still waiting)
        for i in range(armed_idx + 1, len(ltf_df)):
            touched, expired = check_fill(setup, ltf_df, i,
                                           expire_bars=config.PENDING_EXPIRE_BARS)
            if touched:
                outcome = "touched"
                break
            if expired:
                outcome = "expired"
                break

        if outcome == "expired":
            signal.status = "expired"
            session.flush()
        elif outcome == "touched":
            _execute(session, signal, setup, account, symbol)
        # else: still waiting, nothing to do this poll


def _execute(session: Session, signal: Signal, setup: PendingSetup,
             account: Account, symbol: str) -> None:
    spec = SYMBOLS.get(symbol)
    if spec is None:
        signal.status = "skipped_error"
        signal.confidence_error = f"no AccountSpec configured for {symbol}"
        session.flush()
        return

    if _open_or_pending_count(session, account.id, symbol) >= config.MAX_CONCURRENT_PER_SYMBOL:
        signal.status = "skipped_max_concurrent"
        session.flush()
        return

    if not _live_guard_ok(account.mode):
        signal.status = "skipped_error"
        signal.confidence_error = "live trading disabled (ALLOW_LIVE_TRADING=false)"
        session.flush()
        return

    spread = spec.spread_pips * spec.pip
    plan = build_trade_plan(setup, spread=spread, rr=config.DEFAULT_RR, pip=spec.pip)
    if plan is None:
        signal.status = "skipped_error"
        signal.confidence_error = "touched zone produced a micro-stop"
        session.flush()
        return

    try:
        price_now = mt5_client.current_price(symbol, plan.direction)
    except RuntimeError as e:
        signal.status = "skipped_error"
        signal.confidence_error = f"price check failed: {e}"
        session.flush()
        return

    max_slip = plan.stop_distance * MAX_SLIPPAGE_STOP_FRACTION
    if abs(price_now - plan.entry) > max_slip:
        signal.status = "skipped_error"
        signal.confidence_error = (
            f"price moved {abs(price_now - plan.entry) / spec.pip:.1f} pips from "
            f"planned entry before fill -- skipped rather than chased")
        session.flush()
        return

    lots = position_size(
        account.equity, RISK_PER_TRADE_PCT, plan.stop_distance, spec,
        cent_account=CENT_ACCOUNT, min_lot=MIN_LOT, lot_step=LOT_STEP, max_lot=MAX_LOT)
    if lots <= 0:
        signal.status = "skipped_error"
        signal.confidence_error = "broker minimum lot exceeds risk budget"
        session.flush()
        return

    try:
        result = mt5_client.place_market_order(
            symbol, plan.direction, lots, plan.sl, plan.tp,
            deviation=config.ORDER_DEVIATION_POINTS, magic=config.EXECUTION_MAGIC,
            comment=f"FKB {signal.variant}")
    except RuntimeError as e:
        signal.status = "skipped_error"
        signal.confidence_error = f"order_send failed: {e}"
        session.flush()
        return

    trade = create_trade(
        session, account_id=account.id, signal_id=signal.id, symbol=symbol,
        direction=plan.direction, entry_price=result["price"], sl=plan.sl, tp=plan.tp,
        lots_or_qty=lots, broker_order_id=str(result["ticket"]), status="open",
        risk_amount=account.equity * (RISK_PER_TRADE_PCT / 100.0),
        equity_at_entry=account.equity,
    )
    signal.status = "filled"
    signal.trade_id = trade.id
    session.flush()


def sync_open_trades(session: Session, account: Account) -> None:
    """Every poll, check each open Trade against the broker: still open ->
    nothing to do; closed -> pull the closing deal and record pnl."""
    for trade in list_trades(session, account_id=account.id, status="open", limit=500):
        ticket = int(trade.broker_order_id)
        if mt5_client.get_position(ticket) is not None:
            continue  # still open

        deal = mt5_client.get_closed_deal(ticket)
        if deal is None:
            continue  # closed on the broker but history not visible yet -- retry next poll

        trade.status = "closed"
        trade.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        trade.exit_price = deal.price
        trade.pnl = deal.profit
        trade.r_multiple = deal.profit / trade.risk_amount if trade.risk_amount else None
        trade.equity_at_exit = account.equity
        session.flush()

        record_equity_snapshot(
            session, account_id=account.id, equity=account.equity,
            balance=account.balance,
            open_positions_count=mt5_client.open_positions_count())
