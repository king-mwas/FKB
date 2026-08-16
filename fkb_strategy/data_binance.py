"""
Binance candle loading. Public klines endpoint -- no API key needed for
market data. Mirrors fkb_strategy/data_mt5.py's load()/load_recent()
interface so live_engine/detector.py can treat both brokers uniformly.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from fkb_strategy.config import BINANCE_TF_MAP

BASE_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000  # Binance's per-request cap on klines


def _fetch(symbol: str, interval: str, *, limit: int = None,
           start_ms: int = None, end_ms: int = None) -> list:
    params = [f"symbol={symbol}", f"interval={interval}"]
    if limit is not None:
        params.append(f"limit={limit}")
    if start_ms is not None:
        params.append(f"startTime={start_ms}")
    if end_ms is not None:
        params.append(f"endTime={end_ms}")
    url = f"{BASE_URL}?{'&'.join(params)}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def _to_df(rows: list, symbol: str, timeframe: str) -> pd.DataFrame:
    if not rows:
        raise RuntimeError(
            f"No data for {symbol} {timeframe} from Binance. "
            f"Check the symbol is a valid Binance market (e.g. 'BTCUSDT')."
        )
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "qav", "trades", "taker_base", "taker_quote", "ignore"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms")
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]]
    return df.rename(columns={"volume": "tick_volume"})


def load_recent(symbol: str, timeframe: str, n_bars: int) -> pd.DataFrame:
    """
    Pull the most recent n_bars CLOSED candles. Matches data_mt5.load_recent's
    contract: the still-forming current candle is dropped, same as MT5's
    pos=1 skip, so the live engine's no-lookahead guarantee holds for either
    broker.
    """
    interval = BINANCE_TF_MAP[timeframe]
    rows = _fetch(symbol, interval, limit=min(n_bars + 1, MAX_LIMIT))
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if rows and rows[-1][6] > now_ms:  # close_time in the future -> still forming
        rows = rows[:-1]
    return _to_df(rows[-n_bars:], symbol, timeframe)


def load(symbol: str, timeframe: str, years: float) -> pd.DataFrame:
    """
    Pull candles over a historical date range (for backtester parity with
    data_mt5.load), paginating past Binance's 1000-candle-per-request cap.
    """
    interval = BINANCE_TF_MAP[timeframe]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    all_rows = []
    cursor = start_ms
    while cursor < end_ms:
        rows = _fetch(symbol, interval, limit=MAX_LIMIT, start_ms=cursor, end_ms=end_ms)
        if not rows:
            break
        all_rows.extend(rows)
        last_close = rows[-1][6]
        if last_close <= cursor:
            break
        cursor = last_close + 1
        if len(rows) < MAX_LIMIT:
            break
    return _to_df(all_rows, symbol, timeframe)
