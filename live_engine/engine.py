"""
Orchestration: poll -> detect -> dedupe -> arm -> log.

Phase 3 scope only — stops after logging a detected/armed Signal row.
Confidence scoring (Phase 4) and execution (Phase 5) hook in later without
changing this poll loop's shape.
"""

import os
import time
from datetime import datetime

from db.base import get_session
from db.crud import get_or_create_account, set_setting
from fkb_strategy.config import BINANCE_SYMBOLS, SYMBOLS
from live_engine import binance_client, config
from live_engine.confidence import score_signal
from live_engine.detector import poll_track

# MetaTrader5 ships Windows-only wheels and drives a local MT5 terminal, so
# the MT5 tracks simply cannot run on a Linux host. Binance is plain REST and
# can, so probe for the package and drop the MT5 tracks when it's absent
# rather than refusing to start at all -- that's what lets the crypto half of
# the engine run 24/7 on a Linux server. The probe is on MetaTrader5 itself,
# not on the imports below, so a genuine ImportError inside executor.py or
# mt5_client.py still surfaces loudly on Windows instead of silently
# disabling forex.
try:
    import MetaTrader5  # noqa: F401
except ImportError:
    MT5_AVAILABLE = False
    executor = mt5_client = None
else:
    MT5_AVAILABLE = True
    from live_engine import executor, mt5_client

MT5_TRACKS = [t for t in config.TRACKS if t["broker"] == "mt5"] if MT5_AVAILABLE else []
BINANCE_TRACKS = [t for t in config.TRACKS if t["broker"] == "binance"]
ALL_TRACKS = MT5_TRACKS + BINANCE_TRACKS

# config.py validates TRACKS_ENABLED against all four track names -- it can't
# know whether MetaTrader5 is importable here. So a selection naming only MT5
# tracks passes validation there and is emptied by the filter above, leaving an
# engine that starts, polls nothing, and looks like a strategy that never
# fires. Nothing legitimately runs zero tracks, so fail loudly instead.
if not ALL_TRACKS:
    raise RuntimeError(
        "No tracks to poll. TRACKS_ENABLED="
        f"{os.environ.get('TRACKS_ENABLED', '')!r} selected only MT5 tracks, "
        "and MetaTrader5 is not available on this host (Windows-only). "
        "Binance tracks available here: "
        f"{sorted('binance:' + t['name'] for t in config.ALL_KNOWN_TRACKS if t['broker'] == 'binance')}")

TICK_S = 5

# Per-broker: which symbols to poll, how to pre-flight the connection, how
# to sync the account row's balance/equity, and the (mode, label) for
# get_or_create_account. Keeps run_once broker-agnostic.
_BROKER = {
    "binance": {
        "symbols": BINANCE_SYMBOLS,
        "ensure_connected": binance_client.ensure_connected,
        "account_summary": binance_client.account_summary,
        "mode": lambda: config.BINANCE_MODE,
        "label": lambda: f"Binance {config.BINANCE_MODE}",
    },
}

if MT5_AVAILABLE:
    _BROKER["mt5"] = {
        "symbols": SYMBOLS,
        "ensure_connected": mt5_client.ensure_connected,
        "account_summary": mt5_client.account_summary,
        "mode": lambda: config.MT5_MODE,
        "label": lambda: f"MT5 {config.MT5_MODE}",
    }


def run_once(track: dict) -> int:
    """One poll pass for a track, across all symbols configured for its
    broker. Returns the number of new signals created."""
    broker = track["broker"]
    b = _BROKER[broker]
    b["ensure_connected"]()
    total_new = 0

    with get_session() as session:
        account = get_or_create_account(session, broker=broker, mode=b["mode"](),
                                         label=b["label"]())
        info = b["account_summary"]()
        account.balance = info["balance"]
        account.equity = info["equity"]
        account.margin_used = info["margin"]
        account.last_synced_at = datetime.utcnow()

        if broker == "mt5":
            try:
                executor.sync_open_trades(session, account)
            except Exception as e:
                print(f"  ! {track['name']} sync_open_trades: {e}")

        for symbol in b["symbols"]:
            try:
                new_signals, ltf_df = poll_track(session, account.id, track, symbol)
            except Exception as e:
                print(f"  ! {track['name']} {symbol}: {e}")
                continue

            total_new += len(new_signals)
            for sig in new_signals:
                print(f"[{track['name']}] {symbol} {sig.variant} {sig.event_kind} "
                      f"dir={sig.direction:+d} bar={sig.bar_time} "
                      f"zone=({sig.zone_bottom:.5f},{sig.zone_top:.5f})")
                try:
                    score_signal(session, sig, account, track["model"])
                except Exception as e:
                    # score_signal already fails closed internally; this is
                    # only a backstop against a truly unexpected bug so one
                    # signal can't take down the rest of the poll pass.
                    sig.status = "skipped_error"
                    sig.confidence_error = f"unexpected: {type(e).__name__}: {e}"
                    session.flush()
                if sig.status == "confidence_pass":
                    print(f"    -> confidence {sig.confidence_score} (PASS, threshold "
                          f"{config.CONFIDENCE_THRESHOLD})")
                elif sig.confidence_score is not None:
                    print(f"    -> confidence {sig.confidence_score} (below threshold)")
                else:
                    print(f"    -> confidence scoring skipped: {sig.confidence_error}")

            # Execution (Phase 5) is MT5-only for now -- see executor.py's
            # module docstring for why Binance stays inert here.
            if broker == "mt5":
                try:
                    executor.check_fills_and_execute(session, account, track, symbol, ltf_df)
                except Exception as e:
                    print(f"  ! {track['name']} {symbol} check_fills_and_execute: {e}")

        set_setting(session, f"engine_heartbeat:{broker}:{track['name']}",
                    datetime.utcnow().isoformat())

    return total_new


def main_loop():
    if not MT5_AVAILABLE:
        print("FKB live engine: MetaTrader5 unavailable on this host -- "
              "running Binance tracks only, forex tracks disabled.")
    print(f"FKB live engine starting. MT5_MODE={config.MT5_MODE} "
          f"BINANCE_MODE={config.BINANCE_MODE} "
          f"tracks={[(t['broker'], t['name']) for t in ALL_TRACKS]}")
    next_due = {(t["broker"], t["name"]): 0.0 for t in ALL_TRACKS}

    while True:
        now = time.monotonic()
        for track in ALL_TRACKS:
            key = (track["broker"], track["name"])
            if now >= next_due[key]:
                try:
                    run_once(track)
                except Exception as e:
                    # One broker being unreachable (e.g. MT5 terminal not
                    # open) must not take down other tracks/brokers sharing
                    # this loop -- log and retry at the track's own cadence.
                    print(f"  ! {track['broker']}:{track['name']} run_once failed: {e}")
                next_due[key] = now + track["poll_s"]
        time.sleep(TICK_S)
