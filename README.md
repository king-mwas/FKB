# FKB — SMC Strategy, Live Signals, Journal

An SMC (BOS/CHOCH/FVG/Order Block) trading system: a backtester, a live
detection + Claude-confidence-scored auto-execution engine (MT5 + Binance),
and a local website for trades, a journal, screenshots, and P2P tracking.

Full architecture and build plan: see the plan this was built from (ask
Claude Code to recall it, or check `C:\Users\HP\.claude\plans\iterative-singing-comet.md`).

## Project layout

```
fkb_strategy/   shared strategy logic (broker-agnostic) — used by BOTH backtester and live_engine
backtester/     offline historical sweep — smc_backtest.py
live_engine/    standalone service: poll MT5/Binance -> detect -> Claude confidence -> execute -> log
db/             shared SQLAlchemy models (SQLite, WAL mode)
webapp/         FastAPI + Jinja2/htmx site: dashboard, signals, trades, journal, screenshots, P2P log
data/           fkb.db (SQLite) + uploaded screenshots (gitignored)
scripts/        one-off setup/utility scripts
```

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in real values (Anthropic API key,
   MT5 demo/live credentials, Binance testnet/live keys).
3. **Open your MT5 terminal and log in** before running anything that
   touches MT5 — the `MetaTrader5` Python package only works against a
   locally running, logged-in terminal. This machine currently has no
   terminal open, so `mt5.initialize()` will fail with an IPC timeout
   until you start it.
4. Confirm your exact broker symbol names in MT5's Market Watch (brokers
   often suffix symbols, e.g. `EURUSD.`) — run `python scripts/export_mt5_symbols.py`
   once written, or check manually, and update `fkb_strategy/config.py`'s
   `SYMBOLS` dict if they differ from `XAUUSD`/`EURUSD`/`USDJPY`.

## Run the backtester

```
python -m backtester.smc_backtest
```

Sweeps ~200 variant/parameter combos per symbol against MT5 historical
data and writes `smc_results.csv`. Requires a running, logged-in MT5
terminal — this has not been run yet against real data.

**Read the warnings at the bottom of `backtester/smc_backtest.py` before
trusting any number it prints** — overfitting risk, intrabar SL/TP
assumptions, spread-vs-slippage, and the honest-result calibration (a real
edge looks like 40-55% win rate, not 80%).

## MT5 MCP (interactive use only)

`.mcp.json` registers `metatrader-mcp-server` (pip package) so Claude Code
can inspect live MT5 state during chats. It's wired to the **demo**
credentials (`MT5_LOGIN_DEMO`/`MT5_PASSWORD_DEMO`/`MT5_SERVER_DEMO`) by
default, matching the project's demo-first safety default. Those three
values need to be real environment variables (not just in `.env`) for the
`${...}` substitution in `.mcp.json` to resolve — either `export` them in
your shell profile or set them in Windows' environment variables before
launching Claude Code.

This MCP server is **not** in the automated trading path — the live engine
talks to MT5 directly via the `MetaTrader5` Python package, independent of
any chat session. See the operational note in the plan about not running
the live engine and interactive MCP inspection against *different* MT5
accounts at the same time (MT5's terminal session is shared — whichever
login fires most recently wins terminal-wide).

## Live engine (not yet built)

Will run detection + Claude confidence scoring + auto-execution against MT5
and Binance, defaulting to demo/testnet with hard-coded safety guards before
any live order is placed. See the plan for the phased build order — the
current state of this repo has completed the shared-logic extraction and
verified it's behavior-identical to the original script (see
`fkb_strategy/`, `backtester/smc_backtest.py`), but the live engine, DB, and
webapp are not yet implemented.

## Safety

- `MT5_MODE` / `BINANCE_MODE` default to `demo` / `testnet`.
- `ALLOW_LIVE_TRADING` / `ALLOW_LIVE_BINANCE_TRADING` default to `false` and
  are `.env`-only — never exposed in the web UI, so a stray click can never
  flip either account to live money.
- The original script's own advice still applies: forward-test any winning
  variant on a demo account for 4+ weeks before ever considering live.
