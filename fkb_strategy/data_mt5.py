"""
MT5 candle loading. Unchanged logic from FKB.py.txt's load(), renamed for
clarity now that a Binance equivalent (data_binance.py) exists alongside it.

MT5's Python API only works where the MT5 terminal is installed and logged
in — this must run on the same Windows machine as that terminal.
"""

from datetime import datetime, timedelta

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from fkb_strategy.config import TF_MAP


def load(symbol: str, timeframe: str, years: float) -> pd.DataFrame:
    """Pull candles from the local MT5 terminal (historical range)."""
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package missing. Run: pip install MetaTrader5")
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    tf = getattr(mt5, TF_MAP[timeframe])
    end = datetime.now()
    start = end - timedelta(days=365 * years)
    rates = mt5.copy_rates_range(symbol, tf, start, end)
    return _to_df(rates, symbol, timeframe)


def load_recent(symbol: str, timeframe: str, n_bars: int) -> pd.DataFrame:
    """
    Pull the most recent n_bars closed candles from the local MT5 terminal.
    Used by the live engine's rolling-window poll instead of a date range.
    """
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package missing. Run: pip install MetaTrader5")
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    tf = getattr(mt5, TF_MAP[timeframe])
    # pos=1 skips the current, still-forming bar — only closed bars, matching
    # the backtest's no-lookahead design.
    rates = mt5.copy_rates_from_pos(symbol, tf, 1, n_bars)
    return _to_df(rates, symbol, timeframe)


def _to_df(rates, symbol: str, timeframe: str) -> pd.DataFrame:
    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"No data for {symbol} {timeframe}. "
            f"Check the exact symbol name in MT5 Market Watch — "
            f"brokers often add a suffix like '{symbol}.'"
        )
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")[["open", "high", "low", "close", "tick_volume"]]
