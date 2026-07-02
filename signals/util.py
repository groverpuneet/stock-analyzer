"""Shared helpers for the signal pillars."""
import math
import os

import psycopg2
import psycopg2.extras

_DSN = os.environ.get("DATABASE_URL", "postgresql://puneetgrover@localhost/stock_analyzer")


def get_conn():
    return psycopg2.connect(_DSN)


def dict_cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def f(v):
    """Coerce to float, mapping None/NaN/inf -> None."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else x


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class PillarResult:
    """Accumulates a pillar score around a neutral 50 base with reasoning lines.

    add(points, text, icon=auto): shift the score by `points` and record a reason.
    Icons: ✅ supportive, ⚠️ mild caution, ❌ strong negative, ℹ️ informational.
    """

    def __init__(self):
        self.score = 50.0
        self.reasoning: list[str] = []
        self.key_metrics: dict = {}
        self.contrary: list[str] = []
        self._had_data = False

    def add(self, points: float, text: str, icon: str | None = None):
        self._had_data = True
        self.score += points
        if icon is None:
            icon = "✅" if points > 0.5 else "❌" if points < -3 else "⚠️" if points < 0 else "ℹ️"
        self.reasoning.append(f"{icon} {text}")

    def note(self, text: str, icon: str = "ℹ️"):
        self.reasoning.append(f"{icon} {text}")

    def contra(self, text: str):
        self.contrary.append(text)

    def metric(self, key: str, value):
        self.key_metrics[key] = value

    def finalize(self) -> dict:
        return {
            "score": round(clamp(self.score), 1) if self._had_data else None,
            "reasoning": self.reasoning or ["ℹ️ Insufficient data for this pillar"],
            "key_metrics": self.key_metrics,
            "contrary": self.contrary,
        }
