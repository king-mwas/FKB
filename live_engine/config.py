"""
Live engine configuration: detection tracks, safety guards, polling
cadence. Loads .env (see .env.example) — every credential and mode/guard
value comes from there, never hardcoded here.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------- tracks

# Two "how should this setup be judged" tracks per broker: fast-moving
# intraday structure judged by Sonnet, slower daily/weekly structure judged
# by Opus. Phase 3 (this file's first consumer) only runs the mt5 tracks —
# Binance tracks are inert until Phase 8 adds a Binance client/executor.
TRACKS = [
    {"name": "scalp_day", "broker": "mt5", "htf": "H4", "ltf": "M15",
     "model": "claude-sonnet-5", "poll_s": 60},
    {"name": "swing_position", "broker": "mt5", "htf": "D1", "ltf": "H4",
     "model": "claude-opus-5", "poll_s": 900},
    {"name": "scalp_day", "broker": "binance", "htf": "H4", "ltf": "M15",
     "model": "claude-sonnet-5", "poll_s": 60},
    {"name": "swing_position", "broker": "binance", "htf": "D1", "ltf": "H4",
     "model": "claude-opus-5", "poll_s": 900},
]

# Optional subset selection, e.g. TRACKS_ENABLED=binance:swing_position or
# "binance:scalp_day,binance:swing_position". Unset runs every track above.
# An unrecognised entry is fatal rather than ignored: a typo that silently
# filtered every track would leave the engine running, polling nothing, and
# looking like the strategy simply never fires.
ALL_KNOWN_TRACKS = list(TRACKS)  # pre-filter, for error messages

_ENABLED = os.environ.get("TRACKS_ENABLED", "").strip()
if _ENABLED:
    _want = {p.strip() for p in _ENABLED.split(",") if p.strip()}
    _known = {f"{t['broker']}:{t['name']}" for t in ALL_KNOWN_TRACKS}
    _unknown = _want - _known
    if _unknown:
        raise ValueError(
            f"TRACKS_ENABLED names unknown track(s): {sorted(_unknown)}. "
            f"Valid values: {sorted(_known)}")
    TRACKS = [t for t in TRACKS if f"{t['broker']}:{t['name']}" in _want]


VARIANTS = ["CHOCH_OB", "BOS_OB", "BOS_FVG", "SWEEP_CHOCH_OB"]

SWING_LOOKBACK = 3
DEFAULT_RR = 2.0
SESSION_FILTER = True
REQUIRE_HTF_ALIGN = True
PENDING_EXPIRE_BARS = 30

ROLLING_LTF_BARS = 500
ROLLING_HTF_BARS = 300

# ----------------------------------------------------------------- mt5

MT5_MODE = os.environ.get("MT5_MODE", "demo")  # demo | live
ALLOW_LIVE_TRADING = os.environ.get("ALLOW_LIVE_TRADING", "false").lower() == "true"

MT5_LOGIN = os.environ.get(f"MT5_LOGIN_{MT5_MODE.upper()}")
MT5_PASSWORD = os.environ.get(f"MT5_PASSWORD_{MT5_MODE.upper()}")
MT5_SERVER = os.environ.get(f"MT5_SERVER_{MT5_MODE.upper()}")

# ------------------------------------------------------------- binance

BINANCE_MODE = os.environ.get("BINANCE_MODE", "testnet")  # testnet | live
ALLOW_LIVE_BINANCE_TRADING = os.environ.get("ALLOW_LIVE_BINANCE_TRADING", "false").lower() == "true"

BINANCE_API_KEY = os.environ.get(f"BINANCE_API_KEY_{BINANCE_MODE.upper()}")
BINANCE_API_SECRET = os.environ.get(f"BINANCE_API_SECRET_{BINANCE_MODE.upper()}")

# ----------------------------------------------------------- confidence

CONFIDENCE_THRESHOLD = int(os.environ.get("CONFIDENCE_THRESHOLD", "73"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# How many closed LTF candles to show Claude per scoring call.
CONFIDENCE_CANDLE_COUNT = 25
# Spend guard: hard cap on Claude calls per hour, per (broker, track) pair —
# independent of how many symbols/signals fire, since a busy market could
# otherwise arm many setups in a short window.
MAX_CONFIDENCE_CALLS_PER_HOUR = int(os.environ.get("MAX_CONFIDENCE_CALLS_PER_HOUR", "10"))
CONFIDENCE_TIMEOUT_S = 30.0

MAX_CONCURRENT_PER_SYMBOL = 1

# --------------------------------------------------------------- execution

ORDER_DEVIATION_POINTS = int(os.environ.get("ORDER_DEVIATION_POINTS", "20"))
EXECUTION_MAGIC = int(os.environ.get("EXECUTION_MAGIC", "990321"))
