"""backtest/ — quant backtesting foundation.

Phase 0 (data integrity): point-in-time, corp-action-adjusted, survivorship-aware
data access. Phase 1 (engine): vectorbt execution + metrics behind a Strategy
interface. This package owns the PIT/adjustment/survivorship logic regardless of
the downstream engine.
"""
