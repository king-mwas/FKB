"""
Position sizing. Same math as FKB.py.txt's position_size(), refactored to
take account rules as explicit parameters instead of module globals — both
the backtester and the live engine (potentially against different accounts
at once: MT5 demo, MT5 live, Binance) need to pass account state predictably.
"""

import numpy as np

from fkb_strategy.config import AccountSpec


def position_size(equity: float, risk_pct: float, stop_distance: float,
                   spec: AccountSpec, *, cent_account: bool,
                   min_lot: float, lot_step: float, max_lot: float) -> float:
    """
    Lots such that (stop distance x value per point) == risk amount.
    Returns 0.0 if the broker minimum already exceeds the risk budget —
    that is a REAL constraint, not a rounding error. Skipping the trade is
    the correct behaviour; taking it would mean risking more than planned.
    """
    risk_amount = equity * (risk_pct / 100.0)
    contract = spec.contract / 100.0 if cent_account else spec.contract
    value_per_point = contract          # $ per 1.0 price move per 1.0 lot
    risk_per_min_lot = stop_distance * value_per_point * min_lot

    if risk_per_min_lot > risk_amount:
        return 0.0                      # cannot size down far enough — skip

    lots = risk_amount / (stop_distance * value_per_point)
    lots = np.floor(lots / lot_step) * lot_step
    return float(min(max(lots, min_lot), max_lot))
