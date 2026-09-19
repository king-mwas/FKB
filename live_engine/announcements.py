"""
Binance announcement watcher: pushes new giveaway/competition/reward posts to
Telegram.

Separate from the trading path on purpose. This reads a public marketing feed,
needs no API key, touches no account, and can never place a trade -- it only
reads and forwards text.

A caution about the source. Binance's trading API has no promotions endpoint,
so this reads the CMS feed their own website calls. That is undocumented: the
URL, the catalog ids and the response shape can change without notice, and
the host may rate-limit or refuse. Everything about the request is therefore
configurable via .env or app_settings, so a break is a config change rather
than a code change, and every failure is logged and swallowed rather than
raised. Treat delivery as best-effort -- do not rely on it for anything
time-critical.
"""

import html
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi

from db.base import SessionLocal
from db.crud import get_setting, set_setting, setting_or_env
from live_engine import notify

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

DEFAULT_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"

# Binance groups announcements into catalogs. 48 is new listings, 49 is the
# activities/promotions catalog that carries giveaways and competitions.
# UNVERIFIED here -- binance.com is unreachable from the environment this was
# written in. If alerts never arrive, check these ids against the catalogId
# in the URL of a real announcement page and override ANNOUNCE_CATALOGS.
DEFAULT_CATALOGS = "48,49"

DEFAULT_KEYWORDS = ("giveaway,competition,airdrop,launchpool,megadrop,"
                    "learn & earn,learn and earn,reward,bonus,campaign,"
                    "promotion,carnival,contest,quiz,voucher")

# Cap on remembered ids per catalog. Enough to cover far more than one sweep's
# worth of posts, bounded so the app_settings row can't grow without limit.
SEEN_LIMIT = 300


def _cfg(key: str, default: str) -> str:
    return setting_or_env(key, default)


def _fetch(catalog: str, page_size: int = 20) -> list[dict]:
    url = _cfg("ANNOUNCE_URL", DEFAULT_URL)
    query = urllib.parse.urlencode({
        "type": 1, "catalogId": catalog, "pageNo": 1, "pageSize": page_size,
    })
    req = urllib.request.Request(
        f"{url}?{query}",
        # The CMS endpoint serves the website; a default urllib agent is a
        # common thing for it to refuse.
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as r:
        body = json.loads(r.read())
    # Shape: data.catalogs[].articles[] on the catalog query, or data.articles[]
    # depending on the parameters. Accept either rather than assuming one.
    data = body.get("data") or {}
    articles = list(data.get("articles") or [])
    for cat in data.get("catalogs") or []:
        articles.extend(cat.get("articles") or [])
    return articles


def _matches(title: str, keywords: list[str]) -> bool:
    lowered = title.lower()
    return any(k in lowered for k in keywords)


def _article_id(article: dict) -> str:
    for key in ("id", "code", "articleId"):
        value = article.get(key)
        if value not in (None, ""):
            return str(value)
    return article.get("title", "")


def _url_for(article: dict) -> str:
    code = article.get("code") or article.get("id")
    return f"https://www.binance.com/en/support/announcement/{code}" if code else ""


def _format(article: dict) -> str:
    title = html.escape(str(article.get("title", "(untitled)")))
    link = _url_for(article)
    text = f"🎁 <b>Binance</b>\n{title}"
    if link:
        text += f"\n\n{html.escape(link)}"
    return text


def _seen(session, catalog: str) -> tuple[list[str], bool]:
    """Returns (ids, seeded). `seeded` reflects whether the row EXISTS, not
    whether it holds anything: a catalog that legitimately returns no articles
    would otherwise be treated as a first run on every sweep, permanently
    re-arming the seeding branch and hiding a genuinely broken catalog id
    behind a routine-looking message."""
    raw = get_setting(session, f"announce_seen:{catalog}")
    if raw is None:
        return [], False
    try:
        return list(json.loads(raw)), True
    except (json.JSONDecodeError, TypeError):
        return [], True


def check(page_size: int = 20) -> int:
    """One sweep. Returns the number of alerts sent."""
    if not notify.enabled():
        print("  announcements: Telegram not configured, nothing to send to.")
        return 0

    keywords = [k.strip().lower() for k in
                _cfg("ANNOUNCE_KEYWORDS", DEFAULT_KEYWORDS).split(",") if k.strip()]
    catalogs = [c.strip() for c in
                _cfg("ANNOUNCE_CATALOGS", DEFAULT_CATALOGS).split(",") if c.strip()]
    sent = 0

    for catalog in catalogs:
        try:
            articles = _fetch(catalog, page_size)
        except Exception as e:
            print(f"  ! announcements catalog {catalog}: {type(e).__name__}: {e}")
            continue

        with SessionLocal() as session:
            seen, seeded = _seen(session, catalog)
            known = set(seen)
            first_run = not seeded

            fresh = [a for a in articles if _article_id(a) not in known]
            if first_run:
                # Seed silently. Without this the first sweep would fire one
                # message per existing post -- a burst of old news that trains
                # you to ignore the alerts.
                print(f"  announcements catalog {catalog}: first run, "
                      f"remembering {len(articles)} existing post(s), not alerting.")
                delivered = [_article_id(a) for a in articles]
            else:
                delivered = []
                for article in fresh:
                    if not _matches(str(article.get("title", "")), keywords):
                        # Remember non-matching posts too, so they are not
                        # re-examined every sweep.
                        delivered.append(_article_id(article))
                        continue
                    if notify.send_message(_format(article)):
                        delivered.append(_article_id(article))
                        sent += 1
                        print(f"  -> alerted: {article.get('title')}")
                    else:
                        # Leave it unseen so the next sweep retries rather than
                        # dropping an alert on a transient Telegram failure.
                        print(f"  ! send failed, will retry: {article.get('title')}")

            if delivered or not seeded:
                merged = (delivered + seen)[:SEEN_LIMIT]
                set_setting(session, f"announce_seen:{catalog}", json.dumps(merged))
                session.commit()

    return sent
