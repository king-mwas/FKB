"""
Orchestration: poll -> detect -> dedupe -> arm -> log.

Phase 3 scope only — stops after logging a detected/armed Signal row.
Confidence scoring (Phase 4) and execution (Phase 5) hook in later without
changing this poll loop's shape.
"""

import time
from datetime import datetime

from db.base import get_session
from db.crud import get_or_create_account, set_setting
from fkb_strategy.config import BINANCE_SYMBOLS, SYMBOLS
from live_engine import binance_client, config, execution, mt5_client
from live_engine.confidence import score_signal
from live_engine.detector import poll_track

MT5_TRACKS = [t for t in config.TRACKS if t["broker"] == "mt5"]
BINANCE_TRACKS = [t for t in config.TRACKS if t["broker"] == "binance"]
ALL_TRACKS = MT5_TRACKS + BINANCE_TRACKS
TICK_S = 5

# Per-broker: which symbols to poll, how to pre-flight the connection, how
# to sync the account row's balance/equity, and the (mode, label) for
# get_or_create_account. Keeps run_once broker-agnostic.
_BROKER = {
    "mt5": {
        "symbols": SYMBOLS,
        "ensure_connected": mt5_client.ensure_connected,
        "account_summary": mt5_client.account_summary,
        "mode": lambda: config.MT5_MODE,
        "label": lambda: f"MT5 {config.MT5_MODE}",
    },
    "binance": {
        "symbols": BINANCE_SYMBOLS,
        "ensure_connected": binance_client.ensure_connected,
        "account_summary": binance_client.account_summary,
        "mode": lambda: config.BINANCE_MODE,
        "label": lambda: f"Binance {config.BINANCE_MODE}",
    },
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

        for symbol in b["symbols"]:
            try:
                new_signals = poll_track(session, account.id, track, symbol)
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
                    if broker == "mt5":
                        execution.try_execute(session, sig, account)
                    else:
                        print("    -> execution not yet implemented for binance (Phase 8)")
                elif sig.confidence_score is not None:
                    print(f"    -> confidence {sig.confidence_score} (below threshold)")
                else:
                    print(f"    -> confidence scoring skipped: {sig.confidence_error}")

        set_setting(session, f"engine_heartbeat:{broker}:{track['name']}",
                    datetime.utcnow().isoformat())

    return total_new


def main_loop():
    print(f"FKB live engine starting. MT5_MODE={config.MT5_MODE} "
          f"BINANCE_MODE={config.BINANCE_MODE} "
          f"tracks={[(t['broker'], t['name']) for t in ALL_TRACKS]}")
    next_due = {(t["broker"], t["name"]): 0.0 for t in ALL_TRACKS}

    while True:
        now = time.monotonic()
        for track in ALL_TRACKS:
            key = (track["broker"], track["name"])
            if now >= next_due[key]:
                run_once(track)
                next_due[key] = now + track["poll_s"]
        time.sleep(TICK_S)
