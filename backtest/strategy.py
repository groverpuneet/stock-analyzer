"""backtest/strategy.py — pluggable strategy interface for the vectorbt engine.

A Strategy turns (prices, scores) panels into entries/exits boolean panels of the
same shape, which backtest/engine.py feeds straight into vectorbt's
Portfolio.from_signals. This keeps the engine strategy-agnostic: swap the Strategy,
keep the same costs/slippage/risk-metric machinery.
"""
from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "unnamed"

    @abstractmethod
    def generate_signals(self, prices: pd.DataFrame, scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (entries, exits) boolean DataFrames aligned to `prices` shape (index=date,
        columns=symbol). `scores` may be sparser than `prices` (fewer symbols/dates covered
        by signal_explanations) — implementations should reindex_like(prices) and treat
        missing scores as "no opinion" (no entry/exit), never as a bullish/bearish signal."""


class SignalThresholdStrategy(Strategy):
    """Long-only: enter when signals/engine.py's overall_score crosses above buy_threshold,
    exit when it drops below sell_threshold. Reuses signals/ as the alpha model directly —
    this is the reference strategy for the PIT signal replay built in Phase 0c."""

    name = "signal_threshold"

    def __init__(self, buy_threshold: float = 65.0, sell_threshold: float = 45.0):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate_signals(self, prices: pd.DataFrame, scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        aligned = scores.reindex_like(prices)
        above_buy = aligned >= self.buy_threshold
        below_sell = aligned < self.sell_threshold
        entries = above_buy & ~above_buy.shift(1, fill_value=False)
        exits = below_sell & ~below_sell.shift(1, fill_value=False)
        return entries.fillna(False), exits.fillna(False)
