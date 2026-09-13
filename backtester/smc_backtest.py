"""
FKB SMC BACKTESTER — BOS / CHOCH / FVG / Order Block
====================================================

Runs on YOUR machine, against YOUR broker's MT5 historical data.
Outputs REAL numbers per strategy variant, ranked by monthly return.

WHY THIS RUNS ON YOUR MACHINE:
    MT5's Python API only works where the MT5 terminal is installed and
    logged in. That's your laptop, not a server somewhere. It pulls the
    same candle history your charts use — real spreads, real gaps.

SETUP:
    pip install -r requirements.txt
    (MT5 terminal must be OPEN and logged into your account)

RUN:
    python -m backtester.smc_backtest

WHAT IT DOES:
    1. Pulls N years of candles for each symbol
    2. Detects market structure bar-by-bar (no lookahead)
    3. Tests every variant x parameter combo
    4. Ranks by monthly return, shows drawdown + trade count
    5. Writes results to smc_results.csv

READ THE WARNINGS AT THE BOTTOM OF THIS FILE BEFORE TRUSTING ANY NUMBER.

This file is the strategy sweep/backtest ONLY. The core detection logic
(swings, structure, order blocks, FVGs, sweeps, setup arming, position
sizing) lives in fkb_strategy/ and is shared with the live engine — see
that package if you're looking for find_swings(), Structure, etc.
"""

import itertools

import numpy as np
import pandas as pd

from fkb_strategy.config import (
    BINANCE_SPECS, COMMISSION_PER_LOT, CENT_ACCOUNT, LOT_STEP, MAX_LOT,
    MIN_LOT, RISK_PER_TRADE_PCT, STARTING_BALANCE, SYMBOLS,
)
from fkb_strategy import data_binance, data_mt5
from fkb_strategy.setups import arm_setup, build_trade_plan, check_fill
from fkb_strategy.sizing import position_size
from fkb_strategy.structure import Structure, find_swings

YEARS_OF_HISTORY = 3

# Which market to sweep. mt5 needs Windows with a logged-in terminal; binance
# pulls public klines over HTTP and so runs anywhere, which is the only way to
# backtest without that terminal. Both loaders take (symbol, timeframe, years).
MARKETS = {
    "mt5": (SYMBOLS, data_mt5.load),
    "binance": (BINANCE_SPECS, data_binance.load),
}

# ══════════════════════════════════════════════════════════════════
# STRATEGY PARAMETERS TO SWEEP
# ══════════════════════════════════════════════════════════════════

SWEEP = {
    "variant": ["CHOCH_OB", "BOS_OB", "BOS_FVG", "SWEEP_CHOCH_OB"],
    "htf": ["H4", "D1"],              # bias timeframe
    "ltf": ["M15", "M5"],             # entry timeframe
    "swing_lookback": [3, 5],         # fractal strength
    "rr": [2.0, 3.0, 5.0],            # risk:reward target
    "session_filter": [True, False],  # London + NY only
    "require_htf_align": [True, False],
}


# ══════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════

def backtest(ltf_df: pd.DataFrame, htf_df: pd.DataFrame, spec, params: dict) -> dict:
    df = find_swings(ltf_df, params["swing_lookback"])
    htf = find_swings(htf_df, params["swing_lookback"])

    # HTF bias, forward-filled onto LTF timestamps (no lookahead: uses only
    # the HTF bar that had already CLOSED at each LTF timestamp)
    htf_struct = Structure()
    htf_bias = []
    for i in range(len(htf)):
        ph = htf["high"].iat[i - 1] if i > 0 else np.nan
        pl = htf["low"].iat[i - 1] if i > 0 else np.nan
        htf_struct.update(i, htf.iloc[i], ph, pl)
        htf_bias.append(htf_struct.trend)
    bias = pd.Series(htf_bias, index=htf.index).shift(1).reindex(
        df.index, method="ffill").fillna(0)

    struct = Structure()
    equity = STARTING_BALANCE
    peak = equity
    max_dd = 0.0
    trades = []
    open_pos = None
    pending = None                       # armed setup waiting for retracement
    skipped_too_small = 0

    spread = spec.spread_pips * spec.pip

    # Per-symbol overrides where set, else the module-level MT5 defaults.
    cent = CENT_ACCOUNT if spec.cent_account is None else spec.cent_account
    min_lot = MIN_LOT if spec.min_lot is None else spec.min_lot
    lot_step = LOT_STEP if spec.lot_step is None else spec.lot_step
    max_lot = MAX_LOT if spec.max_lot is None else spec.max_lot

    for i in range(len(df)):
        row = df.iloc[i]
        ts = df.index[i]

        # ---- manage open position (conservative intrabar assumption) ----
        if open_pos:
            hit_sl = (row["low"] <= open_pos["sl"] if open_pos["dir"] == 1
                      else row["high"] >= open_pos["sl"])
            hit_tp = (row["high"] >= open_pos["tp"] if open_pos["dir"] == 1
                      else row["low"] <= open_pos["tp"])

            exit_price = None
            if hit_sl and hit_tp:
                exit_price = open_pos["sl"]      # assume worst case
            elif hit_sl:
                exit_price = open_pos["sl"]
            elif hit_tp:
                exit_price = open_pos["tp"]

            if exit_price is not None:
                contract = spec.contract / 100.0 if cent else spec.contract
                pnl = ((exit_price - open_pos["entry"]) * open_pos["dir"]
                       * open_pos["lots"] * contract)
                pnl -= COMMISSION_PER_LOT * open_pos["lots"]
                if spec.fee_pct:
                    # Charged on notional at each side, not once on the
                    # position: a percentage fee is the dominant cost on a
                    # Binance spot round trip and is what makes small-move
                    # setups unprofitable there.
                    qty = open_pos["lots"] * contract
                    pnl -= ((open_pos["entry"] + exit_price) * qty
                            * spec.fee_pct / 100.0)
                equity += pnl
                trades.append({
                    "time": ts, "dir": open_pos["dir"], "pnl": pnl,
                    "r": pnl / open_pos["risk_amt"] if open_pos["risk_amt"] else 0,
                    "equity": equity,
                })
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0)
                open_pos = None
                if equity <= 0:
                    break

        # ---- structure update ----
        ph = df["high"].iat[i - 1] if i > 0 else np.nan
        pl = df["low"].iat[i - 1] if i > 0 else np.nan
        event = struct.update(i, row, ph, pl)

        # ---- arm a setup on the right structural event ----
        if event and not open_pos and pending is None:
            pending = arm_setup(event, df, i, ts, bias.iat[i], params)

        # ---- fill pending setup on retracement into the zone ----
        if pending and not open_pos:
            touched, expired = check_fill(pending, df, i)
            if expired:
                pending = None
            elif touched:
                plan = build_trade_plan(pending, spread, params["rr"], spec.pip)
                if plan:
                    lots = position_size(
                        equity, RISK_PER_TRADE_PCT, plan.stop_distance, spec,
                        cent_account=cent, min_lot=min_lot,
                        lot_step=lot_step, max_lot=max_lot)
                    if lots > 0:
                        contract = spec.contract / 100.0 if cent else spec.contract
                        open_pos = {
                            "dir": plan.direction, "entry": plan.entry,
                            "sl": plan.sl, "tp": plan.tp, "lots": lots,
                            "risk_amt": plan.stop_distance * contract * lots,
                        }
                    else:
                        skipped_too_small += 1
                pending = None

    return summarize(trades, equity, max_dd, df, skipped_too_small, params)


def summarize(trades, equity, max_dd, df, skipped, params) -> dict:
    n = len(trades)
    if n == 0:
        return {**params, "trades": 0, "monthly_pct": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "max_dd_pct": 0.0, "final": equity,
                "expectancy_r": 0.0, "skipped_min_lot": skipped}

    pnls = np.array([t["pnl"] for t in trades])
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    months = max((df.index[-1] - df.index[0]).days / 30.44, 1)

    growth = equity / STARTING_BALANCE
    monthly = ((growth ** (1 / months)) - 1) * 100 if growth > 0 else -100.0

    return {
        **params,
        "trades": n,
        "trades_per_month": round(n / months, 1),
        "monthly_pct": round(monthly, 2),
        "win_rate": round(len(wins) / n * 100, 1),
        "profit_factor": round(wins.sum() / abs(losses.sum()), 2)
                         if len(losses) else float("inf"),
        "expectancy_r": round(np.mean([t["r"] for t in trades]), 3),
        "max_dd_pct": round(max_dd * 100, 1),
        "final": round(equity, 2),
        "skipped_min_lot": skipped,
    }


# ══════════════════════════════════════════════════════════════════
# SWEEP RUNNER
# ══════════════════════════════════════════════════════════════════

def run(market: str = "mt5"):
    if market not in MARKETS:
        raise SystemExit(f"Unknown market {market!r}. Choose from {sorted(MARKETS)}.")
    symbols, load = MARKETS[market]

    keys = list(SWEEP.keys())
    combos = [dict(zip(keys, v)) for v in itertools.product(*SWEEP.values())]
    print(f"Market: {market}. Testing {len(combos)} combos x {len(symbols)} "
          f"symbols = {len(combos) * len(symbols)} backtests\n")

    cache, results = {}, []

    for symbol, spec in symbols.items():
        for idx, params in enumerate(combos, 1):
            try:
                for tf in (params["ltf"], params["htf"]):
                    if (symbol, tf) not in cache:
                        cache[(symbol, tf)] = load(symbol, tf, YEARS_OF_HISTORY)
                res = backtest(cache[(symbol, params["ltf"])],
                               cache[(symbol, params["htf"])], spec, params)
                res["symbol"] = symbol
                res["market"] = market
                results.append(res)
            except Exception as e:
                print(f"  ! {symbol} {params['variant']}: {e}")
            if idx % 10 == 0:
                print(f"  {symbol}: {idx}/{len(combos)}")

    if not results:
        if market == "mt5":
            print("\nNo results. Check MT5 is open and symbol names are exact.")
        else:
            print("\nNo results. Check the Binance symbols are valid spot "
                  "markets and that api.binance.com is reachable.")
        return

    out = pd.DataFrame(results)

    # Only trust variants with enough trades to be statistically meaningful.
    # Under ~30 trades, the "best" result is usually luck, not edge.
    credible = out[out["trades"] >= 30].copy()
    credible = credible.sort_values("monthly_pct", ascending=False)

    print("\n" + "=" * 78)
    print("TOP 15 BY MONTHLY RETURN  (>=30 trades only)")
    print("=" * 78)
    cols = ["symbol", "variant", "htf", "ltf", "rr", "session_filter",
            "trades", "monthly_pct", "win_rate", "profit_factor",
            "max_dd_pct", "expectancy_r"]
    print(credible[cols].head(15).to_string(index=False))

    print("\n" + "=" * 78)
    print("SAME LIST RANKED BY RISK-ADJUSTED RETURN (monthly % / max drawdown)")
    print("A 40%/month variant with 70% drawdown will blow the account before")
    print("the average shows up. This ranking is the one that matters.")
    print("=" * 78)
    credible["return_per_dd"] = (credible["monthly_pct"] /
                                 credible["max_dd_pct"].clip(lower=1))
    print(credible.sort_values("return_per_dd", ascending=False)[
        cols + ["return_per_dd"]].head(15).to_string(index=False))

    dropped = len(out) - len(credible)
    if dropped:
        print(f"\n{dropped} combos excluded: fewer than 30 trades "
              f"(too few to distinguish edge from luck).")

    skipped = out["skipped_min_lot"].sum()
    if skipped:
        print(f"\n[!] {skipped} setups skipped because the broker's minimum lot "
              f"would have risked more than {RISK_PER_TRADE_PCT}% of equity.\n"
              f"    If this number is large, your account is too small for "
              f"this symbol at proper risk. Switch to a Cent account or "
              f"trade a smaller-value instrument.")

    out.to_csv("smc_results.csv", index=False)
    print("\nFull results -> smc_results.csv")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="FKB SMC parameter sweep")
    ap.add_argument("--market", default="mt5", choices=sorted(MARKETS),
                    help="mt5 needs a running Windows terminal; binance "
                         "pulls public klines and runs anywhere")
    run(ap.parse_args().market)


# ══════════════════════════════════════════════════════════════════
# READ THIS BEFORE YOU TRUST ANY NUMBER THIS PRINTS
# ══════════════════════════════════════════════════════════════════
#
# 1. IN-SAMPLE OVERFITTING
#    Sweeping ~200 combos and picking the winner guarantees a good-looking
#    number even from pure noise. Split your history: optimise on years 1-2,
#    then run the winner UNTOUCHED on year 3. If it collapses, it was noise.
#    Change YEARS_OF_HISTORY and re-run to do this manually.
#
# 2. THE INTRABAR PROBLEM
#    When a bar's range contains both your SL and TP, this code assumes SL
#    hit first. That is deliberately pessimistic. Real fills on M5/M15 are
#    somewhere between this and optimistic. Tick-level data would settle it.
#
# 3. SPREAD IS MODELLED, SLIPPAGE IS NOT
#    News spikes on gold can slip 20-50 pips past your stop. Real results
#    will be worse than backtest, especially for tight stops.
#
# 4. SWING CONFIRMATION LAG IS HANDLED
#    Swings are only visible n bars after they form. Most retail SMC
#    backtests ignore this and produce inflated results. This one doesn't.
#
# 5. NO SWAP / OVERNIGHT COSTS
#    Cent accounts are typically swap-free — fine if that's your setup. It
#    would not be on a standard account holding positions for days.
#
# 6. WHAT A HONEST RESULT LOOKS LIKE
#    A genuine mechanical SMC edge on gold typically lands somewhere around
#    40-55% win rate at 1:2-1:3 R:R, with 20-40% max drawdown. If your sweep
#    returns something like 80% win rate or 60%/month, you have a bug or a
#    lookahead leak, not a discovery. Go find it.
#
# 7. FORWARD TEST BEFORE LIVE
#    Run the winning variant on a DEMO account for a minimum of 4 weeks.
#    A backtest is a hypothesis. A forward test is evidence.
