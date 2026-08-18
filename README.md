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
db/             shared SQLAlchemy models (Supabase/Postgres, or SQLite fallback)
webapp/         FastAPI + Jinja2/htmx site: dashboard, signals, trades, journal, screenshots, P2P log
data/           fkb.db (SQLite) + uploaded screenshots (gitignored)
scripts/        one-off setup/utility scripts
```

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in real values (Anthropic API key,
   MT5 demo/live credentials, Binance testnet/live keys). For the database,
   set `DATABASE_URL` to use Supabase, or leave it unset for local SQLite —
   see [Database (Supabase / SQLite)](#database-supabase--sqlite) below.
3. **Open your MT5 terminal and log in** before running anything that
   touches MT5 — the `MetaTrader5` Python package only works against a
   locally running, logged-in terminal. This machine currently has no
   terminal open, so `mt5.initialize()` will fail with an IPC timeout
   until you start it.
4. Confirm your exact broker symbol names in MT5's Market Watch (brokers
   often suffix symbols, e.g. `EURUSD.`) — run `python scripts/export_mt5_symbols.py`
   once written, or check manually, and update `fkb_strategy/config.py`'s
   `SYMBOLS` dict if they differ from `XAUUSD`/`EURUSD`/`USDJPY`.

## Database (Supabase / SQLite)

The app reads and writes through SQLAlchemy (`db/models.py`, `db/crud.py`).
The backend is chosen by one env var:

- **`DATABASE_URL` set** → Postgres (Supabase). All data — accounts,
  signals, trades, journal entries, screenshots, equity snapshots, the P2P
  log — lives in your Supabase project and is browsable directly in
  Supabase's **Table Editor**, not just through this app's pages.
- **`DATABASE_URL` unset** → local SQLite at `FKB_DB_PATH` (default
  `./data/fkb.db`), WAL mode. This is the zero-setup fallback; nothing
  below is required to run the app.

The live engine needs a running MT5 terminal (Windows), so in practice both
the engine and the webapp run on that same machine and connect to Supabase
from there. A hosted build/CI box generally *can't* reach Supabase's
Postgres port (it's IPv6-only on the direct host, and raw-TCP database
connections are commonly firewalled) — use the pooler and run from the
machine the app actually lives on.

### One-time Supabase setup

1. Create a project at [supabase.com](https://supabase.com) and set a
   database password.
2. Grab the **session-mode pooler** connection string: project's **Connect**
   dialog (or **Project Settings → Database**). It's IPv4 and behaves like a
   normal persistent connection, which suits the always-running engine +
   webapp. Replace `[YOUR-PASSWORD]` with your database password. (Ignore
   the Prisma "ORM" tab's `DIRECT_URL`/`DATABASE_URL` split — this app uses
   SQLAlchemy and reads only `DATABASE_URL`.)
3. Put it in `.env` (never commit `.env` — it's gitignored):

   ```
   DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

4. `pip install -r requirements.txt` (includes `psycopg2-binary`).
5. Create the tables, either way:
   - `python scripts/init_db.py` — creates all 8 tables directly via
     SQLAlchemy (non-destructive; safe to re-run), **or**
   - paste `db/schema.sql` into Supabase's **SQL Editor** and run it.
6. Open Supabase's **Table Editor** to confirm the tables appear. From then
   on, every row the engine and webapp write shows up there live.

`db/schema.sql` is generated from `db/models.py` and kept in sync with it —
if the models change, regenerate it rather than hand-editing.

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
