"""
kite_auth/auto_login.py

Automates the Kite Connect daily login flow using Playwright + pyotp.
Reads all credentials from .env — nothing is hardcoded.

Flow:
  1. Open Kite login URL in headless Chromium
  2. Fill user ID + password
  3. Generate current TOTP from KITE_TOTP_SECRET (pyotp)
  4. Submit TOTP
  5. Capture request_token from redirect URL
  6. Exchange for access_token via kiteconnect SDK
  7. Save access_token to .kite_access_token

Required .env vars:
  KITE_API_KEY       — from Kite developer portal
  KITE_API_SECRET    — from Kite developer portal
  KITE_USERNAME      — your Zerodha client ID (e.g. AB1234)
  KITE_PASSWORD      — your Zerodha password
  KITE_TOTP_SECRET   — TOTP secret (from Zerodha 2FA setup, not the 6-digit code)

Usage:
  python kite_auth/auto_login.py
  python kite_auth/auto_login.py --dry-run   # validates env vars only, no browser
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()

log = get_logger(__name__)

TOKEN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    '.kite_access_token'
)

_REQUIRED_VARS = ['KITE_API_KEY', 'KITE_API_SECRET', 'KITE_USERNAME', 'KITE_PASSWORD', 'KITE_TOTP_SECRET']


def _check_env():
    missing = [v for v in _REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required .env vars: {', '.join(missing)}")


def _get_request_token(api_key: str, username: str, password: str, totp_secret: str) -> str:
    """
    Drive headless Chromium through the Kite login flow and return the
    request_token from the post-login redirect URL.
    """
    import pyotp
    from playwright.sync_api import sync_playwright

    from kiteconnect import KiteConnect
    login_url = KiteConnect(api_key=api_key).login_url()
    log.info(f"Opening Kite login URL (headless)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()

        # The post-login redirect points at the app's registered redirect URL
        # (a 127.0.0.1 port that isn't served), so the navigation fails and
        # page.url ends up as "chrome-error://chromewebdata/", losing the token.
        # Capture request_token from the redirect REQUEST itself instead — the
        # browser issues that GET (with ?request_token=...) before it fails to
        # connect, so this is deterministic regardless of the failed navigation.
        captured: dict[str, str] = {}

        def _capture(req):
            if "request_token=" in req.url and "url" not in captured:
                captured["url"] = req.url
        page.on("request", _capture)

        page.goto(login_url, wait_until='networkidle')

        # Step 1: user ID + password
        page.fill('input[id="userid"]', username)
        page.locator('input[id="password"]').type(password, delay=50)
        page.click('button[type="submit"]')

        # Step 2: TOTP — wait for the field to appear
        page.wait_for_timeout(3000)
        totp_code = pyotp.TOTP(totp_secret).now()
        log.info("TOTP generated, submitting...")
        page.locator('input').nth(0).type(totp_code, delay=50)

        # Step 3: wait (up to ~20s) for the redirect request carrying the token
        for _ in range(40):
            if "url" in captured:
                break
            page.wait_for_timeout(500)

        redirect_url = captured.get("url") or page.url
        browser.close()

    match = re.search(r'[?&]request_token=([^&]+)', redirect_url)
    if not match:
        raise RuntimeError(
            f"request_token not found in redirect URL.\n"
            f"Got: {redirect_url}\n"
            f"Check credentials or TOTP secret."
        )
    return match.group(1)


def refresh_token() -> str:
    """
    Full token refresh — open browser, login, exchange for access_token,
    save to .kite_access_token. Returns the new access_token.
    """
    _check_env()

    api_key      = os.getenv('KITE_API_KEY')
    api_secret   = os.getenv('KITE_API_SECRET')
    username     = os.getenv('KITE_USERNAME')
    password     = os.getenv('KITE_PASSWORD')
    totp_secret  = os.getenv('KITE_TOTP_SECRET')

    log.info("=== Kite token refresh starting ===")

    request_token = _get_request_token(api_key, username, password, totp_secret)
    log.info("request_token obtained, exchanging for access_token...")

    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=api_key)
    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session['access_token']

    with open(TOKEN_PATH, 'w') as f:
        f.write(access_token)

    log.info(f"=== Kite token refresh complete — saved to {TOKEN_PATH} ===")
    return access_token


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        _check_env()
        log.info("Dry run — all required env vars present")
        sys.exit(0)

    try:
        refresh_token()
    except Exception as e:
        log.error(f"Token refresh failed: {e}", exc_info=True)
        sys.exit(1)
