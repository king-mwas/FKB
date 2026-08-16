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
import urllib.parse
import urllib.request

import certifi

from live_engine import config

BASE_URL = ("https://testnet.binance.vision" if config.BINANCE_MODE == "testnet"
            else "https://api.binance.com")

# Explicit cafile rather than the OS trust store: some Windows installs
# haven't cached the "Amazon Root CA 1" chain testnet.binance.vision serves,
# which fails cert verification here even though other HTTPS hosts on the
# same machine work fine.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _signed_get(path: str, params: dict = None) -> dict:
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    sig = hmac.new(config.BINANCE_API_SECRET.encode(), query.encode(),
                    hashlib.sha256).hexdigest()
    url = f"{BASE_URL}{path}?{query}&signature={sig}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": config.BINANCE_API_KEY})
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as r:
        return json.loads(r.read())


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


def account_summary() -> dict:
    """Returns zeros (no error) when BINANCE_API_KEY_<mode> / _SECRET_<mode>
    aren't set in .env yet -- only needed for balance display, not
    detection."""
    if not (config.BINANCE_API_KEY and config.BINANCE_API_SECRET):
        return {"balance": 0.0, "equity": 0.0, "margin": 0.0}
    data = _signed_get("/api/v3/account")
    usdt = next((b for b in data.get("balances", []) if b["asset"] == "USDT"), None)
    balance = float(usdt["free"]) + float(usdt["locked"]) if usdt else 0.0
    return {"balance": balance, "equity": balance, "margin": 0.0}
