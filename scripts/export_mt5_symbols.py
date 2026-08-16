"""
Print every symbol visible in the local MT5 terminal's Market Watch,
so you can confirm the exact names/suffixes your broker uses before
trusting fkb_strategy/config.py's SYMBOLS dict.

Run: python scripts/export_mt5_symbols.py [filter]
     python scripts/export_mt5_symbols.py XAU     (only symbols containing "XAU")
"""
import sys

import MetaTrader5 as mt5


def main():
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        print("Make sure the MT5 terminal is open and logged in on this machine.")
        sys.exit(1)

    term_filter = sys.argv[1].upper() if len(sys.argv) > 1 else None
    symbols = mt5.symbols_get()
    if not symbols:
        print("No symbols returned — check the terminal is logged in.")
        mt5.shutdown()
        sys.exit(1)

    names = sorted(s.name for s in symbols)
    if term_filter:
        names = [n for n in names if term_filter in n.upper()]

    print(f"{len(names)} symbols:")
    for n in names:
        print(" ", n)

    mt5.shutdown()


if __name__ == "__main__":
    main()
