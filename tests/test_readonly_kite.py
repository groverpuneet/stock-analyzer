"""Tests for the read-only Kite guardrail. No network / real Kite access."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kite_auth.readonly_kite import KiteWriteBlocked, ReadOnlyKite, wrap_readonly


class DummyKite:
    """Stand-in with both allowed read methods and blocked write methods."""

    def historical_data(self, *a, **k):
        return "historical_data"

    def quote(self, *a, **k):
        return "quote"

    def ltp(self, *a, **k):
        return "ltp"

    def instruments(self, *a, **k):
        return "instruments"

    # These must never be reachable through the wrapper.
    def place_order(self, *a, **k):
        return "place_order"

    def cancel_order(self, *a, **k):
        return "cancel_order"

    def holdings(self, *a, **k):
        return "holdings"

    def positions(self, *a, **k):
        return "positions"

    def funds(self, *a, **k):
        return "funds"

    def place_gtt(self, *a, **k):
        return "place_gtt"


@pytest.fixture
def ro():
    return wrap_readonly(DummyKite())


def test_wrap_returns_readonly():
    assert isinstance(wrap_readonly(DummyKite()), ReadOnlyKite)


@pytest.mark.parametrize("method", ["historical_data", "quote", "ltp", "instruments"])
def test_allowed_methods_pass_through(ro, method):
    assert getattr(ro, method)() == method


@pytest.mark.parametrize(
    "method",
    ["place_order", "cancel_order", "holdings", "positions", "funds", "place_gtt"],
)
def test_blocked_methods_raise(ro, method):
    with pytest.raises(KiteWriteBlocked):
        getattr(ro, method)
