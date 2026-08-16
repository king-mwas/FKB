"""
Live engine entrypoint.

Run: python -m live_engine.run           (loops forever, per-track cadence)
     python -m live_engine.run --once    (one poll pass per track, then exit
                                           — useful for verification)
"""

import sys

from db.base import init_db
from live_engine.engine import ALL_TRACKS, main_loop, run_once


def main():
    init_db()
    if "--once" in sys.argv:
        for track in ALL_TRACKS:
            n = run_once(track)
            print(f"[{track['name']}] poll complete: {n} new signal(s)")
        return
    main_loop()


if __name__ == "__main__":
    main()
