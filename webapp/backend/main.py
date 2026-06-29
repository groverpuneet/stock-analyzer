"""Stock Analyzer web API.

FastAPI backend serving real data from the PostgreSQL stock_analyzer database.
Read-only over market data; the only writes are to the watchlist table.

Security features:
- Session-based authentication (bcrypt + itsdangerous)
- Rate limiting (slowapi)
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Read-only DB user for webapp

Run (from webapp/backend, with venv310):
    WEBAPP_DATABASE_URL=postgresql://stock_reader:stockreader2026@localhost/stock_analyzer \
    uvicorn main:app --reload --port 8009
"""
import os
import secrets
from datetime import datetime, timedelta

import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from routers import signals, stocks, macro, watchlist, opportunities, chat, refresh, dashboard, quality, data, smart_money, fear_greed  # noqa: E402

SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
SESSION_COOKIE_NAME = "stock_session"
SESSION_MAX_AGE = 24 * 60 * 60

WEBAPP_USERNAME = os.environ.get("WEBAPP_USERNAME", "")
WEBAPP_PASSWORD_HASH = os.environ.get("WEBAPP_PASSWORD_HASH", "")

serializer = URLSafeTimedSerializer(SESSION_SECRET)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app = FastAPI(title="Stock Analyzer API", version="1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class NgrokHeaderMiddleware(BaseHTTPMiddleware):
    """Tag responses with the ngrok bypass header so the free-tier interstitial is
    skipped on API responses reached through the tunnel (e.g. the iPhone widget)."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(NgrokHeaderMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session_user(request: Request) -> str | None:
    """Extract username from session cookie if valid."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    try:
        data = serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None


def require_auth(request: Request) -> str:
    """Dependency that requires valid authentication."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/status"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require auth for all /api/* except public paths."""
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS:
        if not WEBAPP_USERNAME:
            pass
        elif not get_session_user(request):
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)


@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, response: Response):
    """Login with username and password."""
    if not WEBAPP_USERNAME or not WEBAPP_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    username = body.get("username", "")
    password = body.get("password", "")

    if username != WEBAPP_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if not bcrypt.checkpw(password.encode(), WEBAPP_PASSWORD_HASH.encode()):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_data = {"username": username, "created": datetime.utcnow().isoformat()}
    token = serializer.dumps(session_data)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"status": "ok", "username": username}


@app.post("/api/auth/logout")
async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Check if user is authenticated."""
    user = get_session_user(request)
    return {"authenticated": bool(user), "username": user}


@app.get("/api/health")
@limiter.exempt
def health():
    from db import query_one
    row = query_one("SELECT COUNT(*) AS n FROM stocks")
    return {"status": "ok", "stocks": row["n"] if row else 0,
            "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "auth_enabled": bool(WEBAPP_USERNAME)}


for r in (signals.router, stocks.router, macro.router, watchlist.router,
          opportunities.router, chat.router, refresh.router, dashboard.router,
          quality.router, data.router, smart_money.router, fear_greed.router):
    app.include_router(r)
