"""
kite_auth/readonly_kite.py

Defense-in-depth guardrail around the Kite Connect SDK.

Kite Connect has no read-only access token, so we enforce read-only-ness in OUR
code: `ReadOnlyKite` wraps an authenticated `KiteConnect` instance and exposes
ONLY an allow-list of market-data / read methods. Any other attribute access --
especially order placement, portfolio, positions, holdings, funds, GTT, etc. --
raises `KiteWriteBlocked`, so even a bug or a compromised code path physically
cannot trade or read brokerage account state.
"""

# Exactly the read/data methods the app uses. Default is deny; add here only
# after confirming a method is purely read-only market data.
_ALLOWED = frozenset({
    # market data / instruments (read-only)
    "historical_data",
    "quote",
    "ltp",
    "ohlc",
    "instruments",
    "mf_instruments",
    # auth setup -- token setup should happen pre-wrap, but keep these usable
    "set_access_token",
    "generate_session",
    "login_url",
})


class KiteWriteBlocked(Exception):
    """Raised when a blocked (non-read-only) Kite method or attribute is accessed."""


class ReadOnlyKite:
    """Read-only proxy over an authenticated KiteConnect instance.

    Only attributes/methods in the allow-list pass through to the wrapped
    client; everything else raises KiteWriteBlocked.
    """

    def __init__(self, kite):
        # Store on the instance dict directly so __getattr__ isn't triggered
        # for our own bookkeeping attribute.
        object.__setattr__(self, "_kite", kite)

    def __getattr__(self, name):
        # __getattr__ is only called when normal attribute lookup fails, so
        # "_kite" (set via object.__setattr__) never reaches here.
        if name in _ALLOWED:
            return getattr(object.__getattribute__(self, "_kite"), name)
        raise KiteWriteBlocked(
            f"Blocked non-read Kite call: {name}() -- this app is read-only by policy"
        )

    def __setattr__(self, name, value):
        # Disallow mutating the proxy / underlying client through the wrapper.
        raise KiteWriteBlocked(
            f"Blocked non-read Kite call: {name}() -- this app is read-only by policy"
        )

    def __repr__(self):
        return f"ReadOnlyKite({object.__getattribute__(self, '_kite')!r})"


def wrap_readonly(kite):
    """Wrap an authenticated KiteConnect instance in a read-only proxy."""
    return ReadOnlyKite(kite)
