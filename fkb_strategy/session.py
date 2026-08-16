"""Trading session filter. Unchanged logic from FKB.py.txt."""


def in_session(ts) -> bool:
    """London 07:00-16:00 UTC, New York 12:00-21:00 UTC."""
    h = ts.hour
    return (7 <= h < 16) or (12 <= h < 21)
