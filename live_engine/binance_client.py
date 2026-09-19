"""
Binance connection/account helpers for the live engine. Distinct from
fkb_strategy/data_binance.py (public market data, no auth needed) -- this
module is only for the authenticated account-balance sync, and degrades
gracefully when no API key is configured yet: signal detection works fine
without one, only the account row's balance/equity stay at zero.
"""

import hashlib
import hmac
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi

from db.crud import setting_or_env
from live_engine import config

BASE_URL = ("https://testnet.binance.vision" if config.BINANCE_MODE == "testnet"
            else "https://api.binance.com")

# Explicit cafile rather than the OS trust store: some Windows installs
# haven't cached the "Amazon Root CA 1" chain testnet.binance.vision serves,
# which fails cert verification here even though other HTTPS hosts on the
# same machine work fine.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def credentials() -> tuple[str, str]:
    """Read-only key/secret, resolved per call so they can be pasted into
    Supabase rather than edited into a .env on the host."""
    mode = config.BINANCE_MODE.upper()
    return (setting_or_env(f"BINANCE_API_KEY_{mode}", config.BINANCE_API_KEY or ""),
            setting_or_env(f"BINANCE_API_SECRET_{mode}", config.BINANCE_API_SECRET or ""))


def _signed_get(path: str, params: dict = None) -> dict:
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    api_key, api_secret = credentials()
    sig = hmac.new(api_secret.encode(), query.encode(),
                    hashlib.sha256).hexdigest()
    url = f"{BASE_URL}{path}?{query}&signature={sig}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Binance returns the real reason as {"code":-1021,"msg":"..."} in the
        # body; the status line is always a bare "400 Bad Request". Without
        # this, a clock-skew rejection, a revoked key and an IP restriction
        # all look identical and none of them are actionable.
        raise RuntimeError(
            f"Binance {path} -> HTTP {e.code}: {e.read().decode()[:300]}") from e


def ensure_connected():
    """No persistent session for REST -- best-effort ping of the account
    endpoint's host, mirroring mt5_client.ensure_connected()'s role as a
    pre-flight check. Non-fatal: detection (fkb_strategy/data_binance.py,
    always api.binance.com regardless of mode) doesn't depend on this
    succeeding, so a testnet outage or local TLS-trust-store gap shouldn't
    take down signal polling over a balance-sync nicety."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/v3/ping")
        urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT).read()
    except Exception as e:
        print(f"  ! binance_client.ensure_connected: {e}")


ZERO_BALANCE = {"balance": 0.0, "equity": 0.0, "margin": 0.0}


def account_summary() -> dict:
    """Balance for display. Never raises: this is a nicety, and detection --
    which runs off the public klines endpoint and needs no key at all -- must
    not stop because a signed balance read was rejected. ensure_connected()
    above is non-fatal for the same reason; this one was not, so a single 400
    from /api/v3/account aborted the entire poll pass before any symbol was
    examined, and the loop reported only "HTTP Error 400: Bad Request"."""
    if not all(credentials()):
        return dict(ZERO_BALANCE)
    try:
        data = _signed_get("/api/v3/account")
    except Exception as e:
        print(f"  ! binance_client.account_summary: {e}")
        print("    (balance display only -- detection continues)")
        return dict(ZERO_BALANCE)
    usdt = next((b for b in data.get("balances", []) if b["asset"] == "USDT"), None)
    balance = float(usdt["free"]) + float(usdt["locked"]) if usdt else 0.0
    return {"balance": balance, "equity": balance, "margin": 0.0}
