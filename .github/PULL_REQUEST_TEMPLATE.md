## What changed and why

## How was this tested?

- [ ] Backtester still produces identical `smc_results.csv` output (if `fkb_strategy/` touched)
- [ ] Ran against MT5 demo / Binance testnet (if `live_engine/` touched)
- [ ] Manually checked the webapp page(s) affected

## Safety checklist (if this touches execution/config)

- [ ] `MT5_MODE`/`BINANCE_MODE` defaults untouched (`demo`/`testnet`)
- [ ] `ALLOW_LIVE_TRADING`/`ALLOW_LIVE_BINANCE_TRADING` defaults untouched (`false`)
- [ ] No secrets committed (`.env`, API keys, credentials)
