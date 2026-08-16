"""
Order block / fair value gap / liquidity sweep detection.

Unchanged logic from the original FKB.py.txt backtester.
"""

import pandas as pd


def find_order_block(df: pd.DataFrame, break_idx: int, direction: int,
                      lookback: int = 20):
    """
    Order block = last opposing candle before the impulse that broke structure.
    Bullish break -> last DOWN candle before the move up.
    Returns (ob_high, ob_low) or None.
    """
    lo = max(0, break_idx - lookback)
    for j in range(break_idx - 1, lo, -1):
        o, c = df["open"].iat[j], df["close"].iat[j]
        if direction == 1 and c < o:              # bearish candle
            return df["high"].iat[j], df["low"].iat[j]
        if direction == -1 and c > o:             # bullish candle
            return df["high"].iat[j], df["low"].iat[j]
    return None


def find_fvg(df: pd.DataFrame, break_idx: int, direction: int,
             lookback: int = 15):
    """
    Fair Value Gap: 3-candle imbalance.
    Bullish FVG -> candle[i-2].high < candle[i].low (untouched gap).
    Returns (gap_top, gap_bottom) or None.
    """
    lo = max(2, break_idx - lookback)
    for j in range(break_idx, lo, -1):
        if direction == 1 and df["high"].iat[j - 2] < df["low"].iat[j]:
            return df["low"].iat[j], df["high"].iat[j - 2]
        if direction == -1 and df["low"].iat[j - 2] > df["high"].iat[j]:
            return df["low"].iat[j - 2], df["high"].iat[j]
    return None


def had_liquidity_sweep(df: pd.DataFrame, i: int, direction: int,
                         lookback: int = 12) -> bool:
    """
    Liquidity sweep = wick takes out a recent extreme, body closes back inside.
    Bullish setup wants a sweep of lows (stop hunt) before the bullish break.
    """
    lo = max(1, i - lookback)
    window = df.iloc[lo:i]
    if len(window) < 3:
        return False
    if direction == 1:
        ref = window["low"].iloc[:-2].min()
        recent = window.iloc[-2:]
        return bool(((recent["low"] < ref) & (recent["close"] > ref)).any())
    ref = window["high"].iloc[:-2].max()
    recent = window.iloc[-2:]
    return bool(((recent["high"] > ref) & (recent["close"] < ref)).any())
