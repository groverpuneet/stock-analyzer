"""Portfolio authentication — a second, stricter gate on top of the main session.

Every /api/portfolio/* request must satisfy ALL of:
  1. localhost origin   (is_localhost) — blocks ngrok / any external access
  2. main session       (the puneet login cookie)
  3. portfolio session  (TOTP verified within the last 15 minutes)

The portfolio session is a short-lived signed cookie (`portfolio_session`, 15-min TTL)
issued only after a valid TOTP code. It is signed with PORTFOLIO_ENCRYPTION_KEY (stable
across restarts, unlike the possibly-ephemeral main SESSION_SECRET).
"""
import os
from datetime import datetime, timezone

import pyotp
from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from portfolio_db import audit

PORTFOLIO_TOTP_SECRET = os.environ.get("PORTFOLIO_TOTP_SECRET", "")
_SIGN_KEY = os.environ.get("PORTFOLIO_ENCRYPTION_KEY", "") or "portfolio-fallback-secret"

PORTFOLIO_COOKIE = "portfolio_session"
PORTFOLIO_TTL_SECONDS = 15 * 60  # 15 minutes

_serializer = URLSafeTimedSerializer(_SIGN_KEY, salt="portfolio-session")

_LOOPBACK = {"127.0.0.1", "::1"}
# Any of these headers means the request arrived via a proxy/tunnel (ngrok, CDN, …).
_FORWARD_HEADERS = ("x-forwarded-host", "x-real-ip", "cf-connecting-ip", "forwarded")


def is_localhost(request: Request) -> bool:
    """True only for genuine loopback requests. ngrok forwards to 127.0.0.1 too, so the
    TCP peer alone is insufficient — we also reject any proxy/tunnel forwarding headers.
    The local Vite proxy uses changeOrigin WITHOUT xfwd, so local requests carry none."""
    client = request.client.host if request.client else ""
    if client not in _LOOPBACK:
        return False
    xff = request.headers.get("x-forwarded-for")
    if xff and any(ip.strip() and ip.strip() not in _LOOPBACK for ip in xff.split(",")):
        return False
    if any(request.headers.get(h) for h in _FORWARD_HEADERS):
        return False
    return True


def verify_totp(code: str) -> bool:
    if not PORTFOLIO_TOTP_SECRET or not code:
        return False
    code = str(code).strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    # valid_window=1 tolerates ~30s clock skew either side.
    return pyotp.TOTP(PORTFOLIO_TOTP_SECRET).verify(code, valid_window=1)


def issue_portfolio_token() -> str:
    return _serializer.dumps({"v": 1, "iat": datetime.now(timezone.utc).isoformat()})


def portfolio_session_valid(request: Request) -> bool:
    cookie = request.cookies.get(PORTFOLIO_COOKIE)
    if not cookie:
        return False
    try:
        _serializer.loads(cookie, max_age=PORTFOLIO_TTL_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_portfolio(request: Request) -> str:
    """Dependency for every portfolio endpoint: localhost + main session + TOTP session.

    Assumes the global auth middleware already enforced the main session for /api/*.
    """
    if not is_localhost(request):
        audit("blocked_external", _client_ip(request), f"path={request.url.path}")
        raise HTTPException(status_code=403, detail="Portfolio is accessible from localhost only")
    if not portfolio_session_valid(request):
        raise HTTPException(status_code=401, detail="Portfolio TOTP verification required")
    return "portfolio"
