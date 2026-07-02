"""Four-pillar explainable signal engine (Session L).

Pillars (each returns a 0-100 score where 50 = neutral, >50 bullish, <50 bearish,
plus plain-English reasoning, key metrics, and contrary indicators):

  technical   — trend / RSI / MACD / Bollinger / volume / OBV / VWAP
  fundamental — valuation / quality / growth / earnings / analyst / ownership
  flows       — FII·DII / insider / bulk·SAST·13F·MF / options / news / trends
  external    — fresh web + Google-News sentiment (VADER), cached 6h
  advisor     — placeholder (Pillar 5), weight 0 for now

`combiner` reweights the pillars per horizon (SHORT/MID/LONG) into an overall
signal; `engine` orchestrates compute + persistence to signal_explanations.
"""
