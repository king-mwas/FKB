"""
Signal dedup: has this exact (account, symbol, ltf, variant, event_kind,
bar_time) fingerprint already been recorded? Backed by the DB's own unique
constraint (see db/models.py Signal.__table_args__) — this module is just
the read-side check so the detector can skip re-arming work it's already
done, and so an engine restart resumes cleanly from the DB's own history
instead of re-firing signals already scored or traded.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from db.crud import find_signal_by_fingerprint


def already_seen(session: Session, *, account_id: int, symbol: str, ltf: str,
                  variant: str, event_kind: str, bar_time: datetime) -> bool:
    return find_signal_by_fingerprint(
        session, account_id, symbol, ltf, variant, event_kind, bar_time
    ) is not None
