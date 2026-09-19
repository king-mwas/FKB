"""
Setup doctor: checks everything FKB needs before a first run, and says which
part is at fault when something is missing.

    python scripts/check_setup.py

Read-only. Places no orders, sends no Telegram message, spends no API credit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OK, BAD, WARN = "  [OK]  ", "  [FAIL]", "  [warn]"


def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    return f"{value[:6]}...{value[-4:]} ({len(value)} chars)"


def check_candles() -> bool:
    print("\nBinance market data (public, no API key)")
    from fkb_strategy.config import BINANCE_SYMBOLS
    from fkb_strategy.data_binance import load_recent
    all_ok = True
    for symbol in BINANCE_SYMBOLS:
        try:
            df = load_recent(symbol, "H4", 30)
            print(f"{OK} {symbol:<10} {len(df):>3} H4 candles, last close {df['close'].iloc[-1]}")
        except Exception as e:
            all_ok = False
            print(f"{BAD} {symbol:<10} {type(e).__name__}: {e}")
    return all_ok


def check_database():
    print("\nDatabase")
    try:
        from db.base import SessionLocal, init_db
        init_db()
        with SessionLocal() as session:
            session.execute(__import__("sqlalchemy").text("select 1"))
        url = os.environ.get("DATABASE_URL", "")
        print(f"{OK} connected ({'Postgres/Supabase' if url else 'local SQLite'})")
        return True
    except Exception as e:
        print(f"{BAD} {type(e).__name__}: {e}")
        return False


def check_config():
    """Placeholder detection matters: a leftover 'PASTE_...' value is truthy,
    so the code treats it as configured and fails at call time instead of
    staying inert."""
    print("\nCredentials (app_settings, falling back to .env)")
    from db.crud import setting_or_env
    from live_engine import config

    rows = [
        ("ANTHROPIC_API_KEY", "signal scoring", True),
        ("TELEGRAM_BOT_TOKEN", "alerts to your phone", True),
        ("TELEGRAM_CHAT_ID", "alerts to your phone", True),
        (f"BINANCE_API_KEY_{config.BINANCE_MODE.upper()}", "balance display only", False),
        (f"BINANCE_API_SECRET_{config.BINANCE_MODE.upper()}", "balance display only", False),
    ]
    required_ok = True
    for key, purpose, required in rows:
        value = setting_or_env(key, "")
        placeholder = value.upper().startswith(("PASTE", "YOUR_", "SK-ANT-API03-YOUR"))
        if placeholder:
            print(f"{BAD} {key:<26} PLACEHOLDER {value!r} -- worse than empty, "
                  f"the code will treat this as configured and fail at call time")
            required_ok = required_ok and not required
        elif value:
            print(f"{OK} {key:<26} {_mask(value)}")
        else:
            mark = BAD if required else WARN
            print(f"{mark} {key:<26} not set ({purpose})")
            required_ok = required_ok and not required
    return required_ok


def main():
    print("=" * 68)
    print("FKB setup check")
    print("=" * 68)
    candles = check_candles()
    database = check_database()
    creds = check_config() if database else False

    print("\n" + "=" * 68)
    if candles and database and creds:
        print("Ready. Next: python -m live_engine.run --announcements")
    else:
        print("Not ready yet:")
        if not candles:
            print("  - market data unreachable (network, or a bad symbol)")
        if not database:
            print("  - database unreachable (check DATABASE_URL in .env)")
        elif not creds:
            print("  - required credentials missing or still placeholders")
    print("=" * 68)
    return 0 if (candles and database and creds) else 1


if __name__ == "__main__":
    sys.exit(main())
