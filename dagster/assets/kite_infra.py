"""kite_infra group — daily Kite Connect access-token refresh."""
from dagster import asset


@asset(
    group_name="kite_infra",
    description="Daily Kite Connect access token via Playwright + pyotp. Saved to .kite_access_token.",
)
def kite_token_refreshed(context) -> None:
    from kite_auth.auto_login import refresh_token
    refresh_token()
    context.log.info("Kite token refreshed and saved to .kite_access_token")
