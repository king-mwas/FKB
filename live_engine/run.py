"""
Live engine entrypoint.

Run: python -m live_engine.run           (loops forever, per-track cadence)
     python -m live_engine.run --once    (one poll pass per track, then exit
                                           — useful for verification)
     python -m live_engine.run --announcements
                                         (one Binance announcement sweep, then
                                           exit — independent of trading, so it
                                           suits its own slower cron entry)
"""

import sys

from db.base import init_db
from live_engine.engine import ALL_TRACKS, main_loop, run_once


def main():
    init_db()
    if "--announcements" in sys.argv:
        # Deliberately not folded into the poll loop: it reads a public
        # marketing feed, needs no account, and wants a much slower cadence
        # than market polling.
        from live_engine.announcements import check
        print(f"announcement sweep: {check()} alert(s) sent")
        return
    if "--once" in sys.argv:
        for track in ALL_TRACKS:
            try:
                n = run_once(track)
                print(f"[{track['name']}] poll complete: {n} new signal(s)")
            except Exception as e:
                print(f"[{track['name']}] poll failed: {e}")
        return
    main_loop()


if __name__ == "__main__":
    main()
