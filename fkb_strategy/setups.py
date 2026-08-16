"""
Setup arming + trade-plan construction.

NEW extraction (not present as separate functions in the original
FKB.py.txt) — pulled out of backtest()'s inline arming logic (which variant
wants which event kind, HTF-align check, session filter, zone lookup) and
its fill/trade-plan construction (entry/SL/TP from a touched zone).

This is the single most important refactor for correctness: the backtester
and the live engine both call these same functions, so live detection can
never silently drift from what was actually backtested.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from fkb_strategy.session import in_session
from fkb_strategy.zones import find_fvg, find_order_block, had_liquidity_sweep


@dataclass
class PendingSetup:
    variant: str
    kind: str            # "BOS" | "CHOCH"
    direction: int        # 1 (long) | -1 (short)
    zone_type: str         # "OB" | "FVG"
    top: float
    bottom: float
    armed_at: int          # bar index the setup was armed at


@dataclass
class TradePlan:
    direction: int
    entry: float
    sl: float
    tp: float
    stop_distance: float


def variant_wants(variant: str, kind: str, direction: int,
                   df: pd.DataFrame, i: int) -> bool:
    """Does this variant care about this event kind (and, for the sweep
    variant, is there sweep evidence)?"""
    return (
        (variant == "CHOCH_OB" and kind == "CHOCH") or
        (variant == "BOS_OB" and kind == "BOS") or
        (variant == "BOS_FVG" and kind == "BOS") or
        (variant == "SWEEP_CHOCH_OB" and kind == "CHOCH"
         and had_liquidity_sweep(df, i, direction))
    )


def arm_setup(event: tuple, df: pd.DataFrame, i: int, ts,
              bias_at_i: int, params: dict) -> Optional[PendingSetup]:
    """
    Given a structure event (kind, direction) at bar i, decide whether this
    variant's rules are satisfied and — if so — locate its zone (OB or FVG).
    Returns None if the event doesn't arm a setup under these params.
    """
    kind, direction = event
    variant = params["variant"]

    if not variant_wants(variant, kind, direction, df, i):
        return None
    if params.get("session_filter") and not in_session(ts):
        return None
    if params.get("require_htf_align") and bias_at_i != direction:
        return None

    zone_type = "FVG" if variant == "BOS_FVG" else "OB"
    zone = (find_fvg(df, i, direction) if zone_type == "FVG"
            else find_order_block(df, i, direction))
    if not zone:
        return None

    top, bottom = zone
    return PendingSetup(variant=variant, kind=kind, direction=direction,
                         zone_type=zone_type, top=top, bottom=bottom,
                         armed_at=i)


def check_fill(pending: PendingSetup, df: pd.DataFrame, i: int,
               expire_bars: int = 30) -> tuple[bool, bool]:
    """
    Check whether bar i's range touches the pending setup's zone.
    Returns (touched, expired).
    """
    if i - pending.armed_at > expire_bars:
        return False, True
    row = df.iloc[i]
    d = pending.direction
    touched = (row["low"] <= pending.top if d == 1
               else row["high"] >= pending.bottom)
    return bool(touched and i > pending.armed_at), False


def build_trade_plan(pending: PendingSetup, spread: float, rr: float,
                      pip: float, min_stop_pip_mult: float = 3.0
                      ) -> Optional[TradePlan]:
    """
    Given a touched pending setup, compute entry/SL/TP. Returns None if the
    resulting stop distance is an absurd micro-stop (noise, not a real
    trade) — same guard as the original backtest.
    """
    d = pending.direction
    entry = pending.top + spread if d == 1 else pending.bottom - spread
    sl = pending.bottom if d == 1 else pending.top
    stop_dist = abs(entry - sl)
    if stop_dist <= pip * min_stop_pip_mult:
        return None
    tp = entry + d * stop_dist * rr
    return TradePlan(direction=d, entry=entry, sl=sl, tp=tp,
                      stop_distance=stop_dist)
