"""backtest/engine.py — Phase 1 vectorized EOD backtest engine (vectorbt-backed).

run_backtest() is the one public entry point: resolve a PIT universe + price/signal
panels (backtest/data_provider.py), hand them to a Strategy (backtest/strategy.py) to
get entries/exits, run vectorbt with costs+slippage, compute risk metrics, and persist
the run + equity curve + trades into the `backtest` schema (migration 0028).
"""
import json
from datetime import date

import numpy as np
import pandas as pd
import vectorbt as vbt

from backtest.strategy import Strategy
from utils.db import get_conn

TRADING_DAYS_PER_YEAR = 252


def _compute_metrics(pf: vbt.Portfolio, initial_capital: float) -> dict:
    equity = pf.value()
    n_days = len(equity)
    total_return = float(pf.total_return())
    years = n_days / TRADING_DAYS_PER_YEAR if n_days else 0
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else None

    trades = pf.trades.records_readable
    hit_rate = float(pf.trades.win_rate()) if len(trades) else None
    # Turnover proxy: total traded notional / average portfolio value, annualized.
    turnover = None
    if len(trades) and equity.mean() > 0:
        traded_notional = (trades["Size"].abs() * trades["Avg Entry Price"]).sum() \
            + (trades["Size"].abs() * trades["Avg Exit Price"].fillna(trades["Avg Entry Price"])).sum()
        turnover = float(traded_notional / equity.mean() / years) if years > 0 else None

    return {
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if cagr is not None else None,
        "sharpe_ratio": _safe_float(pf.sharpe_ratio()),
        "sortino_ratio": _safe_float(pf.sortino_ratio()),
        "max_drawdown_pct": _safe_float(pf.max_drawdown() * 100),
        "hit_rate_pct": round(hit_rate * 100, 2) if hit_rate is not None else None,
        "turnover_annualized": round(turnover, 2) if turnover is not None else None,
        "num_trades": int(len(trades)),
        "final_equity": round(float(equity.iloc[-1]), 2) if n_days else initial_capital,
    }


def _safe_float(x):
    x = float(x)
    return round(x, 4) if np.isfinite(x) else None


def _persist(name: str, strategy: Strategy, watchlist: str, stocks: list[dict],
             start: date, end: date, initial_capital: float, fees_pct: float,
             slippage_pct: float, params: dict, metrics: dict, pf: vbt.Portfolio) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO backtest.runs
                       (name, strategy_name, params, universe, start_date, end_date,
                        initial_capital, fees_pct, slippage_pct, metrics, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completed') RETURNING id""",
                (name, strategy.name, json.dumps(params),
                 json.dumps({"watchlist": watchlist, "stock_ids": [s["id"] for s in stocks],
                             "symbols": [s["symbol"] for s in stocks]}),
                 start, end, initial_capital, fees_pct, slippage_pct, json.dumps(metrics)),
            )
            run_id = cur.fetchone()[0]

            equity = pf.value()
            equity_rows = [(run_id, d.date(), round(float(v), 2)) for d, v in equity.items()]
            cur.executemany(
                "INSERT INTO backtest.equity_curve (run_id, date, equity) VALUES (%s,%s,%s) "
                "ON CONFLICT (run_id, date) DO NOTHING", equity_rows,
            )

            trades = pf.trades.records_readable
            trade_rows = []
            symbol_to_id = {s["symbol"]: s["id"] for s in stocks}
            for _, t in trades.iterrows():
                symbol = t["Column"]
                trade_rows.append((
                    run_id, symbol_to_id.get(symbol), symbol,
                    t["Entry Timestamp"].date() if pd.notna(t["Entry Timestamp"]) else None,
                    t["Exit Timestamp"].date() if pd.notna(t["Exit Timestamp"]) else None,
                    round(float(t["Avg Entry Price"]), 4) if pd.notna(t["Avg Entry Price"]) else None,
                    round(float(t["Avg Exit Price"]), 4) if pd.notna(t["Avg Exit Price"]) else None,
                    round(float(t["Size"]), 4) if pd.notna(t["Size"]) else None,
                    round(float(t["PnL"]), 2) if pd.notna(t["PnL"]) else None,
                    round(float(t["Return"]) * 100, 4) if pd.notna(t["Return"]) else None,
                ))
            if trade_rows:
                cur.executemany(
                    """INSERT INTO backtest.trades
                           (run_id, stock_id, symbol, entry_date, exit_date,
                            entry_price, exit_price, size, pnl, return_pct)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", trade_rows,
                )
        conn.commit()
        return run_id
    finally:
        conn.close()


def run_backtest(strategy: Strategy, start: date, end: date, watchlist: str = "Default",
                  horizon: str = "MID", initial_capital: float = 1_000_000.0,
                  fees_pct: float = 0.001, slippage_pct: float = 0.0005,
                  name: str | None = None) -> dict:
    """Run `strategy` over `watchlist`'s PIT universe between start/end and persist the result.

    Returns {"run_id": int, "metrics": dict}. Multi-asset portfolio uses shared cash
    (cash_sharing=True) so total capital is fixed across the whole universe, not
    multiplied per symbol.
    """
    from backtest.data_provider import load_universe, load_price_panel, load_signal_panel

    stocks = load_universe(watchlist, end)
    prices = load_price_panel(stocks, start, end)
    scores = load_signal_panel(stocks, start, end, horizon)

    prices = prices.dropna(axis=1, how="all")
    if prices.empty:
        raise ValueError(f"No price data for watchlist={watchlist!r} between {start} and {end}")

    entries, exits = strategy.generate_signals(prices, scores)
    prices_filled = prices.ffill()

    pf = vbt.Portfolio.from_signals(
        prices_filled, entries, exits,
        fees=fees_pct, slippage=slippage_pct,
        init_cash=initial_capital, cash_sharing=True, group_by=True,
        freq="D",  # trading-day index isn't a fixed-offset freq vectorbt can infer (e.g. 'B')
    )

    metrics = _compute_metrics(pf, initial_capital)
    params = {"buy_threshold": getattr(strategy, "buy_threshold", None),
              "sell_threshold": getattr(strategy, "sell_threshold", None),
              "horizon": horizon}
    run_id = _persist(name or f"{strategy.name} {start}->{end}", strategy, watchlist, stocks,
                       start, end, initial_capital, fees_pct, slippage_pct, params, metrics, pf)
    return {"run_id": run_id, "metrics": metrics}
