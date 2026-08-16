# Contributing

This is a personal trading-automation project (SMC strategy, live MT5/Binance
execution, local journal webapp). It's not currently seeking outside
contributors, but if you're working on it with me or forking it:

## Ground rules

- **Never commit secrets.** `.env` is gitignored — real API keys, MT5
  credentials, and Anthropic keys must never end up in a commit. Copy
  `.env.example` and fill in your own.
- **Demo/testnet first.** `MT5_MODE`/`BINANCE_MODE` default to
  `demo`/`testnet`, and `ALLOW_LIVE_TRADING`/`ALLOW_LIVE_BINANCE_TRADING`
  default to `false`. Don't submit changes that alter these defaults.
- **Don't touch `fkb_strategy/`'s core logic** (`structure.py`, `zones.py`,
  `setups.py`) without re-running the backtester and confirming output
  hasn't silently changed — the backtester and live engine both depend on
  this logic staying identical.
- **Read the warnings in `backtester/smc_backtest.py`** before trusting any
  number it prints, and apply the same honesty calibration in any code that
  touches confidence scoring or performance reporting.

## Workflow

1. Open an issue describing the change before starting non-trivial work.
2. Keep PRs scoped to one concern — a bug fix shouldn't bundle a refactor.
3. If your change touches `live_engine/` or `fkb_strategy/`, describe how you
   tested it (which phase of the build order it hits) in the PR description.

## Setup

See [README.md](README.md) for environment setup and how to run the
backtester.
