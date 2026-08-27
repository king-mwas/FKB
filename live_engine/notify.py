"""
Telegram alerts for signals that clear the confidence threshold.

The point is to remove the dashboard from the critical path: a passing setup
is pushed to the phone with everything needed to place the trade by hand, so
nothing has to be running and reachable for you to act on a signal.

Inert when unconfigured -- no token means no alerts and no errors, mirroring
binance_client.account_summary()'s behaviour with no API key.
"""

import html
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi

from live_engine import config

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

_ARROW = {1: "LONG", -1: "SHORT"}


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _format(signal, account) -> str:
    """HTML rather than MarkdownV2: MarkdownV2 requires escaping a long list
    of characters that appear routinely in reasoning text, and one missed
    escape makes Telegram reject the whole message. HTML needs only three."""
    e = html.escape
    direction = _ARROW.get(signal.direction, str(signal.direction))
    lines = [
        f"<b>{e(signal.symbol)} — {direction}</b>  ({signal.confidence_score}%)",
        f"{e(signal.variant)} · {e(signal.event_kind)} · {e(signal.ltf)} entry, "
        f"{e(signal.htf)} bias",
        f"Zone ({e(signal.zone_type)}): {signal.zone_bottom:.5f} – {signal.zone_top:.5f}",
    ]
    if not signal.session_ok:
        lines.append("⚠️ Outside London/NY sessions")
    if signal.sweep_confirmed:
        lines.append("Liquidity sweep confirmed")
    if signal.confidence_reasoning:
        lines.append(f"\n{e(signal.confidence_reasoning)}")
    if signal.confidence_concerns:
        try:
            concerns = json.loads(signal.confidence_concerns)
        except (json.JSONDecodeError, TypeError):
            concerns = []
        if concerns:
            joined = "\n".join(f"• {e(str(c))}" for c in concerns)
            lines.append(f"\n<b>Concerns</b>\n{joined}")
    lines.append(
        f"\n<i>{e(account.label)} · placed manually — the engine does not "
        f"execute on Binance</i>")
    return "\n".join(lines)


def send_signal(signal, account) -> None:
    """Best-effort. A Telegram outage must not abort the poll pass or leave a
    scored signal unsaved, so every failure is logged and swallowed."""
    if not enabled():
        return
    payload = urllib.parse.urlencode({
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": _format(signal, account),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    url = API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    try:
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as r:
            body = json.loads(r.read())
        if not body.get("ok"):
            print(f"  ! telegram rejected the message: {body}")
    except urllib.error.HTTPError as e:
        # Telegram puts the actual reason (bad chat_id, bot blocked, ...) in
        # the body, not the status line -- printing only the status would make
        # a misconfigured chat_id look like a generic network fault.
        print(f"  ! telegram HTTP {e.code}: {e.read()[:200]!r}")
    except Exception as e:
        print(f"  ! telegram send failed: {type(e).__name__}: {e}")
