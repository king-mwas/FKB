"""
Single-user login for the webapp.

Every route here reads or writes trading data, and several accept writes
(journal entries, allocation, screenshot upload, settings), so the whole app
sits behind one password rather than protecting routes piecemeal.

Secure by default: the app refuses to start without FKB_PASSWORD unless
FKB_ALLOW_NO_AUTH=true is set explicitly. Running open is a deliberate
localhost choice, never the accident of an unset variable -- this app is
meant to be reachable from a phone, which means reachable from the internet.
"""

import hmac
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

PASSWORD = os.environ.get("FKB_PASSWORD", "")
ALLOW_NO_AUTH = os.environ.get("FKB_ALLOW_NO_AUTH", "false").lower() == "true"
AUTH_ENABLED = bool(PASSWORD)

# Paths reachable without a session: the login form itself, its POST target,
# and static assets (the login page's own CSS would otherwise 302 to /login).
PUBLIC_PATHS = frozenset({"/login", "/logout"})
PUBLIC_PREFIXES = ("/static/",)

# Answered with 401 rather than a redirect: these are fetched by XHR/htmx, and
# a 303 to the login page would swap a whole HTML document into a status badge
# instead of failing visibly.
XHR_PREFIXES = ("/api/", "/partials/")


def secret_key() -> str:
    """Signing key for the session cookie. A random per-boot key would log the
    user out on every restart, so it comes from .env; the random fallback only
    applies when auth is off and no session is ever issued."""
    key = os.environ.get("FKB_SECRET_KEY", "")
    if key:
        return key
    if AUTH_ENABLED:
        raise RuntimeError(
            "FKB_SECRET_KEY is not set. It signs the session cookie -- without "
            "a stable value every restart would invalidate your login. Generate "
            "one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    return secrets.token_urlsafe(32)


def check_startup() -> None:
    """Fail fast rather than silently serving an open app on a public host."""
    if AUTH_ENABLED or ALLOW_NO_AUTH:
        return
    raise RuntimeError(
        "FKB_PASSWORD is not set, so the webapp would serve trading data and "
        "accept writes from anyone who can reach it. Set FKB_PASSWORD in .env, "
        "or set FKB_ALLOW_NO_AUTH=true if this really is a localhost-only run.")


def password_ok(candidate: str) -> bool:
    """compare_digest so a wrong password's rejection time doesn't leak how
    many leading characters were right."""
    return hmac.compare_digest(candidate.encode(), PASSWORD.encode())


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


async def require_login(request: Request, call_next):
    """Gate every non-public route. Browsers get a redirect to the login form;
    XHR callers (/api/, /partials/) get 401 JSON, since redirecting an XHR to
    an HTML page just produces a confusing 200 full of markup."""
    if not AUTH_ENABLED or is_public(request.url.path):
        return await call_next(request)
    if request.session.get("authed"):
        return await call_next(request)
    if request.url.path.startswith(XHR_PREFIXES):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return RedirectResponse("/login", status_code=303)
