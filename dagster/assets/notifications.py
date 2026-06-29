"""notifications group — outbound alerts (Telegram).

telegram_daily_digest pushes the morning digest (Fear&Greed, top signals, risk
alerts, FII/DII, earnings this week, top news, macro) to the configured chat at
08:00 IST. It reads the already-materialized DB tables, so it runs after the
overnight/weekly pipelines have landed their data. Send failures are logged to
STATUS.md and surfaced as a Dagster failure (never a raw traceback to Telegram).
"""
from dagster import asset


@asset(
    group_name="notifications",
    description=(
        "Push the morning digest to Telegram via send_daily_digest() — Fear&Greed, "
        "top composite-score signals, risk alerts, FII/DII, earnings (next 7d), top "
        "news by sentiment, and the macro snapshot. Requires TELEGRAM_BOT_TOKEN + "
        "TELEGRAM_CHAT_ID in the environment."
    ),
)
def telegram_daily_digest(context) -> None:
    from data_collectors.telegram_bot import send_daily_digest
    result = send_daily_digest()
    if result["sent"]:
        context.log.info(f"Telegram digest sent ({result['length']} chars)")
    else:
        # Not configured or Telegram API error — already logged to STATUS.md.
        raise RuntimeError(
            "Telegram digest not sent — check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID "
            "and STATUS.md for details."
        )
