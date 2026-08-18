"""
Live structure detection: one poll pass per (track, symbol).

Stateless-recompute, stateful-dedup (see the plan): re-fetch the last
ROLLING_LTF_BARS/ROLLING_HTF_BARS closed candles on every poll and rerun
find_swings()+Structure() over the whole window fresh (cheap, well under
10ms) rather than maintain incremental per-bar state. Only bars whose
(account, symbol, ltf, variant, event_kind, bar_time) fingerprint isn't
already in the DB turn into new Signal rows — this also makes an engine
restart safe: it just re-derives the same events and skips the ones
already recorded.
"""

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from db.crud import create_signal
from fkb_strategy import data_binance, data_mt5
from fkb_strategy.session import in_session
from fkb_strategy.setups import arm_setup
from fkb_strategy.structure import Structure, find_swings, run_structure
from fkb_strategy.zones import had_liquidity_sweep
from live_engine import config
from live_engine.dedup import already_seen

# Per-broker candle loader, keyed by track["broker"] -- keeps poll_track
# broker-agnostic so it never has to branch on broker itself.
LOADERS = {"mt5": data_mt5.load_recent, "binance": data_binance.load_recent}


def compute_htf_bias(htf_df: pd.DataFrame, swing_lookback: int) -> pd.Series:
    """Same no-lookahead bias construction as the backtester: HTF Structure
    trend, shifted forward one bar so only an already-CLOSED HTF bar's bias
    is ever visible, then forward-filled onto whatever index it's reindexed
    against."""
    htf = find_swings(htf_df, swing_lookback)
    struct = Structure()
    trend = []
    for i in range(len(htf)):
        ph = htf["high"].iat[i - 1] if i > 0 else np.nan
        pl = htf["low"].iat[i - 1] if i > 0 else np.nan
        struct.update(i, htf.iloc[i], ph, pl)
        trend.append(struct.trend)
    return pd.Series(trend, index=htf.index).shift(1)


def poll_track(session: Session, account_id: int, track: dict, symbol: str) -> tuple:
    """Fetch fresh data for one (track, symbol), detect structure events,
    arm any variant whose rules are satisfied, and create Signal rows for
    ones not already seen. Returns (new_signals, ltf_df) -- the ltf_df is
    handed back so executor.check_fills_and_execute() can re-check
    already-armed setups against the same freshly fetched window instead
    of re-fetching it."""
    ltf, htf = track["ltf"], track["htf"]
    load_recent = LOADERS[track["broker"]]

    ltf_df = load_recent(symbol, ltf, config.ROLLING_LTF_BARS)
    htf_df = load_recent(symbol, htf, config.ROLLING_HTF_BARS)

    bias_series = compute_htf_bias(htf_df, config.SWING_LOOKBACK)
    bias = bias_series.reindex(ltf_df.index, method="ffill").fillna(0)

    ltf_swings, events = run_structure(ltf_df, config.SWING_LOOKBACK)

    new_signals = []
    for kind, direction, i in events:
        bar_time = ltf_swings.index[i].to_pydatetime()
        ts = ltf_swings.index[i]
        bias_at_i = int(bias.iat[i])
        sweep = had_liquidity_sweep(ltf_swings, i, direction)

        for variant in config.VARIANTS:
            if already_seen(session, account_id=account_id, symbol=symbol,
                             ltf=ltf, variant=variant, event_kind=kind,
                             bar_time=bar_time):
                continue

            params = {
                "variant": variant,
                "session_filter": config.SESSION_FILTER,
                "require_htf_align": config.REQUIRE_HTF_ALIGN,
            }
            pending = arm_setup((kind, direction), ltf_swings, i, ts, bias_at_i, params)
            if pending is None:
                continue

            signal = create_signal(
                session, account_id=account_id, symbol=symbol, ltf=ltf, htf=htf,
                track=track["name"], variant=variant, event_kind=kind,
                direction=direction, bar_time=bar_time, htf_bias=bias_at_i,
                session_ok=in_session(ts), zone_type=pending.zone_type,
                zone_top=pending.top, zone_bottom=pending.bottom,
                sweep_confirmed=sweep, status="detected",
            )
            new_signals.append(signal)

    return new_signals, ltf_df
