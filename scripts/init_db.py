"""
Create data/fkb.db and all tables if they don't already exist. Safe to
re-run — non-destructive.

Run: python scripts/init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.base import DB_PATH, init_db


def main():
    init_db()
    print(f"DB ready at {DB_PATH}")


if __name__ == "__main__":
    main()
