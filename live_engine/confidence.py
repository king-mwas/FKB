"""
Claude confidence scoring for detected setups (Phase 4).

Single-shot structured-output call per new Signal (client.messages.parse,
not a tool-use loop) -- this is judgment/classification, not an agentic
task. Model routing is by track: Sonnet 5 for scalp_day, Opus 5 for
swing_position (see live_engine/config.py TRACKS).

Fail closed, always: any API error, timeout, malformed/out-of-range
confidence value, or spend-guard rate limit means no trade -- the Signal is
marked skipped/errored, never treated as an ambiguous pass. This module
only scores; execution (Phase 5) reads the resulting status separately.
"""

import json
from datetime import datetime, timedelta
from typing import List, Literal, Optional

import anthropic
import pandas as pd
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from db.crud import get_setting, list_equity_snapshots, list_trades, set_setting
from db.models import Account, Signal
from fkb_strategy import data_binance, data_mt5
from fkb_strategy.config import SYMBOLS
from fkb_strategy.setups import PendingSetup, build_trade_plan
from live_engine import config

LOADERS = {"mt5": data_mt5.load_recent, "binance": data_binance.load_recent}

_client: Optional[anthropic.Anthropic] = None


class ConfidenceResult(BaseModel):
    confidence: int = Field(ge=0, le=100)
    direction: Literal["long", "short"]
    htf_aligned: bool
    reasoning: str
    concerns: List[str]


class ConfidenceError(Exception):
    """Any failure that must fail closed (no trade)."""


class RateLimited(ConfidenceError):
    pass


SYSTEM_PROMPT = """You are a risk-averse trading analyst judging a single \
Smart Money Concepts (SMC) setup for a small MT5/Binance account. Score how \
much you would personally trust this specific setup, right now, on a 0-100 \
confidence scale.

Calibration (read carefully, this matters): this strategy's own backtested \
track record is a 40-55% win rate at 1:2-1:3 risk:reward. That is a GOOD, \
real result for SMC-style trading -- most individual setups are mediocre \
or bad even within a profitable strategy. An 80%+ hit rate on your scores \
would mean your calibration is broken, not that the strategy improved. Do \
not inflate scores to be encouraging or agreeable. A typical well-formed \
setup with no red flags should land in the 50-70 range. Reserve 73+ for \
setups with genuinely strong, converging evidence: clean HTF alignment, a \
high-quality zone, correct session timing, sweep confirmation where \
relevant, and nothing in the visible candles that contradicts the read. It \
is normal and expected for most setups to fall below the 73 execution \
threshold -- do not treat that as a failure to find something to praise.

Respond only with your structured judgment. Put any hedging or doubt in \
`concerns`, not in `reasoning` disclaimers."""


def _client_or_raise() -> anthropic.Anthropic:
    global _client
    if not config.ANTHROPIC_API_KEY:
        raise ConfidenceError("ANTHROPIC_API_KEY not set in .env")
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _call_claude(model: str, user_content: str) -> ConfidenceResult:
    """The actual API call, isolated so tests can monkeypatch this one
    function instead of the whole Anthropic client."""
    client = _client_or_raise()
    response = client.with_options(
        timeout=config.CONFIDENCE_TIMEOUT_S, max_retries=2,
    ).messages.parse(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_format=ConfidenceResult,
    )
    return response.parsed_output


def _check_rate_limit(session: Session, track_name: str, broker: str) -> None:
    """Sliding-window spend guard, persisted in app_settings so it survives
    engine restarts. Raises RateLimited (fail closed) rather than silently
    over-spending when a busy market arms many setups at once."""
    key = f"confidence_calls:{broker}:{track_name}"
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=1)
    raw = get_setting(session, key, "[]")
    try:
        stamps = [datetime.fromisoformat(s) for s in json.loads(raw)]
    except (json.JSONDecodeError, ValueError):
        stamps = []
    stamps = [s for s in stamps if s >= cutoff]
    if len(stamps) >= config.MAX_CONFIDENCE_CALLS_PER_HOUR:
        raise RateLimited(
            f"{len(stamps)} confidence calls in the last hour for "
            f"{broker}:{track_name} (limit {config.MAX_CONFIDENCE_CALLS_PER_HOUR})"
        )
    stamps.append(now)
    set_setting(session, key, json.dumps([s.isoformat() for s in stamps]))


def _trade_preview(signal: Signal) -> Optional[str]:
    """Best-effort entry/SL/TP/RR preview built from the signal's zone,
    using the symbol's AccountSpec if one is configured. Returns None for
    symbols with no spec yet (e.g. Binance pairs -- sizing/spec work is
    Phase 8) rather than guessing at pip/spread values."""
    spec = SYMBOLS.get(signal.symbol)
    if spec is None:
        return None
    pending = PendingSetup(
        variant=signal.variant, kind=signal.event_kind, direction=signal.direction,
        zone_type=signal.zone_type, top=signal.zone_top, bottom=signal.zone_bottom,
        armed_at=0,
    )
    spread = spec.spread_pips * spec.pip
    plan = build_trade_plan(pending, spread=spread, rr=config.DEFAULT_RR, pip=spec.pip)
    if plan is None:
        return "Zone touched would produce a micro-stop (likely noise) -- no viable trade plan."
    return (f"Preview entry {plan.entry:.5f}, SL {plan.sl:.5f}, TP {plan.tp:.5f}, "
            f"stop distance {plan.stop_distance / spec.pip:.1f} pips, "
            f"planned RR {config.DEFAULT_RR:.1f}")


def _account_context(session: Session, account: Account) -> str:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    trades_today = sum(
        1 for t in list_trades(session, account_id=account.id, limit=200)
        if t.opened_at >= today
    )
    snapshots = list_equity_snapshots(session, account_id=account.id, limit=500)
    peak_equity = max((s.equity for s in snapshots), default=account.equity)
    drawdown_pct = (
        max(0.0, (peak_equity - account.equity) / peak_equity * 100.0)
        if peak_equity > 0 else 0.0
    )
    return (f"Account equity: {account.equity:.2f}, balance: {account.balance:.2f}, "
            f"trades opened today: {trades_today}, current drawdown from peak: "
            f"{drawdown_pct:.1f}%")


def _candles_block(symbol: str, ltf: str, broker: str) -> str:
    load_recent = LOADERS[broker]
    df: pd.DataFrame = load_recent(symbol, ltf, config.CONFIDENCE_CANDLE_COUNT)
    lines = [
        f"{ts:%Y-%m-%d %H:%M} O:{r.open:.5f} H:{r.high:.5f} L:{r.low:.5f} C:{r.close:.5f}"
        for ts, r in df.iterrows()
    ]
    return "\n".join(lines)


def build_user_prompt(session: Session, signal: Signal, account: Account) -> str:
    direction_label = "long" if signal.direction == 1 else "short"
    bias_label = {1: "long", -1: "short", 0: "neutral"}[signal.htf_bias]
    preview = _trade_preview(signal)
    candles = _candles_block(signal.symbol, signal.ltf, account.broker)

    parts = [
        f"Symbol: {signal.symbol} ({account.broker})",
        f"Setup: {signal.variant} on a {signal.event_kind} event, direction {direction_label}",
        f"HTF ({signal.htf}) bias: {bias_label}",
        f"Session filter: {'in an active session' if signal.session_ok else 'OUTSIDE the London/NY sessions'}",
        f"Zone: {signal.zone_type} [{signal.zone_bottom:.5f}, {signal.zone_top:.5f}]",
        f"Liquidity sweep confirmed: {signal.sweep_confirmed}",
        f"Trade plan preview: {preview or 'unavailable -- no spec configured for this symbol yet'}",
        _account_context(session, account),
        f"Last {config.CONFIDENCE_CANDLE_COUNT} closed {signal.ltf} candles (oldest first):",
        candles,
    ]
    return "\n".join(parts)


def score_signal(session: Session, signal: Signal, account: Account, model: str) -> None:
    """Score one detected Signal in place and persist the outcome. Never
    raises -- every failure path (rate limit, API error, malformed output)
    is caught here and written to the Signal as a fail-closed status so one
    bad call can't take down the rest of a poll pass."""
    broker = account.broker
    try:
        _check_rate_limit(session, signal.track, broker)
        user_content = build_user_prompt(session, signal, account)
        result = _call_claude(model, user_content)
    except RateLimited as e:
        signal.status = "skipped_rate_limited"
        signal.confidence_error = str(e)
        session.flush()
        return
    except (anthropic.APIError, ValidationError, ValueError, RuntimeError) as e:
        signal.status = "skipped_error"
        signal.confidence_error = f"{type(e).__name__}: {e}"
        session.flush()
        return

    signal.confidence_score = result.confidence
    signal.confidence_reasoning = result.reasoning
    signal.confidence_concerns = json.dumps(result.concerns)
    signal.confidence_error = None
    signal.status = ("confidence_pass" if result.confidence >= config.CONFIDENCE_THRESHOLD
                      else "skipped_confidence")
    session.flush()
