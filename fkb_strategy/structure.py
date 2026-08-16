"""
Market structure detection: fractal swings + BOS/CHOCH state machine.

Unchanged logic from the original FKB.py.txt backtester — extracted verbatim
so the backtester and the live engine can never silently diverge on what
counts as a structure break.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def find_swings(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Fractal swing points. A swing high needs n lower highs on BOTH sides,
    which means it is only CONFIRMED n bars later. We shift the confirmation
    forward so the caller never sees a swing before it was knowable.
    """
    h, l = df["high"].values, df["low"].values
    sh = np.zeros(len(df), dtype=bool)
    sl = np.zeros(len(df), dtype=bool)

    for i in range(n, len(df) - n):
        window_h = h[i - n:i + n + 1]
        window_l = l[i - n:i + n + 1]
        if h[i] == window_h.max() and (window_h == h[i]).sum() == 1:
            sh[i] = True
        if l[i] == window_l.min() and (window_l == l[i]).sum() == 1:
            sl[i] = True

    out = df.copy()
    out["swing_high"] = sh
    out["swing_low"] = sl
    # confirmation lag: we only "know" about the swing n bars afterwards
    out["sh_known"] = pd.Series(sh, index=df.index).shift(n).fillna(False)
    out["sl_known"] = pd.Series(sl, index=df.index).shift(n).fillna(False)
    return out


@dataclass
class Structure:
    """Bar-by-bar market structure state machine."""
    trend: int = 0                    # 1 bullish, -1 bearish, 0 undefined
    last_sh: float = np.nan           # last confirmed swing high price
    last_sl: float = np.nan           # last confirmed swing low price
    last_sh_idx: int = -1
    last_sl_idx: int = -1
    events: list = field(default_factory=list)   # ("BOS"|"CHOCH", dir, idx)

    def update(self, i: int, row, prev_high: float, prev_low: float):
        """
        Feed one bar. Returns an event tuple if BOS/CHOCH fired on this bar.

        BOS   = break in the SAME direction as current trend (continuation)
        CHOCH = first break AGAINST the current trend (character change)
        """
        event = None
        close = row["close"]

        # Register newly-confirmed swings (already lag-adjusted)
        if row["sh_known"] and not np.isnan(prev_high):
            self.last_sh, self.last_sh_idx = prev_high, i
        if row["sl_known"] and not np.isnan(prev_low):
            self.last_sl, self.last_sl_idx = prev_low, i

        # Bullish break: close above last swing high
        if not np.isnan(self.last_sh) and close > self.last_sh:
            event = ("BOS", 1) if self.trend == 1 else ("CHOCH", 1)
            self.trend = 1
            self.last_sh = np.nan          # consumed

        # Bearish break: close below last swing low
        elif not np.isnan(self.last_sl) and close < self.last_sl:
            event = ("BOS", -1) if self.trend == -1 else ("CHOCH", -1)
            self.trend = -1
            self.last_sl = np.nan

        if event:
            self.events.append((event[0], event[1], i))
        return event


def run_structure(df: pd.DataFrame, swing_lookback: int) -> tuple[pd.DataFrame, list]:
    """
    Convenience wrapper: find_swings() + a full Structure() pass over df.
    Returns (df_with_swings, list_of_(kind, direction, bar_index)).

    Used by the live engine's stateless-recompute detector — cheap enough
    (well under 10ms for a few hundred bars) to rerun on every poll rather
    than maintain incremental bar-by-bar state.
    """
    df = find_swings(df, swing_lookback)
    struct = Structure()
    events = []
    for i in range(len(df)):
        row = df.iloc[i]
        ph = df["high"].iat[i - 1] if i > 0 else np.nan
        pl = df["low"].iat[i - 1] if i > 0 else np.nan
        event = struct.update(i, row, ph, pl)
        if event:
            events.append((event[0], event[1], i))
    return df, events
