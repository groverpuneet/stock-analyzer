"""
data_collectors/telegram_bot.py  (Session H)

A Telegram bot for the stock-analyzer with three faces:

  1. Daily morning digest (8:00 AM IST) — pushed by the telegram_daily_digest
     Dagster asset, which calls send_daily_digest(). Fear&Greed, top signals,
     risk alerts, FII/DII, earnings this week, top news, macro snapshot.

  2. Rule-based commands (instant, no AI) — /top5, /fear, /macro, /alerts,
     /earnings, /news, /signal SBIN, /fundamentals SBIN, /insider SBIN,
     /watchlist, /help, /start.

  3. AI natural-language queries — any non-command text. context_builder builds a
     compact, relevant-only context block; we ask Gemini first (50 req/day free),
     fall back to Groq (Llama 3.3 70B) on quota/error, and finally to a rule-based
     apology so the user always gets a reply.

Run the interactive listener:   python data_collectors/telegram_bot.py
Send one digest now (test):     python data_collectors/telegram_bot.py --digest

Ground rule: public market data only. Never portfolio / holdings / P&L / positions.
No raw tracebacks are ever sent to Telegram; errors are logged to STATUS.md.
"""
import os
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv

from data_collectors import context_builder as cb

load_dotenv()
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

AI_SYSTEM_PROMPT = (
    "You are a quantitative equity analyst for Indian (NSE) and US markets, embedded "
    "in a Telegram bot. Answer the user's question using ONLY the DATA CONTEXT provided "
    "(latest figures from the user's PostgreSQL database). Be concise — 2-6 short "
    "sentences, cite the numbers you use. If the context lacks what's needed, say so "
    "plainly rather than guessing. You analyse public market data only: never give "
    "personalised financial advice, position sizing, or buy/sell instructions."
)

COMMANDS_HELP = (
    "📋 Commands\n"
    "/top5 — top 5 stocks by composite score\n"
    "/fear — Fear & Greed (India + US)\n"
    "/macro — macro snapshot (VIX, PCR, FII/DII, repo, forex)\n"
    "/alerts — today's risk alerts\n"
    "/earnings — earnings in the next 14 days\n"
    "/news — top news by sentiment today\n"
    "/signal SBIN — signal details for a stock\n"
    "/fundamentals SBIN — PE, PB, ROE, D/E, market cap\n"
    "/insider SBIN — recent insider trades\n"
    "/watchlist — watchlist stocks with composite score\n"
    "/help — show this list\n\n"
    "💬 Or just ask anything, e.g. \"Why is SBIN looking strong?\""
)


# ----------------------------------------------------------------- STATUS.md logging
def log_status(message: str) -> None:
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "STATUS.md")
        with open(path, "a") as fh:
            fh.write(f"\n- [telegram_bot {datetime.now():%Y-%m-%d %H:%M}] {message}")
    except Exception:  # noqa: BLE001 — logging must never crash the bot
        log.warning("Could not append to STATUS.md")


# ----------------------------------------------------------------- Telegram I/O
def send_message(text: str, chat_id: str | None = None) -> bool:
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured")
        return False
    # Telegram caps messages at 4096 chars
    for chunk in (text[i:i + 4000] for i in range(0, max(len(text), 1), 4000)):
        try:
            r = requests.post(f"{API}/sendMessage",
                              json={"chat_id": chat_id, "text": chunk,
                                    "disable_web_page_preview": True},
                              timeout=20)
            if r.status_code != 200:
                log.error(f"sendMessage failed {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:  # noqa: BLE001
            log.error(f"sendMessage error: {e}")
            return False
    return True


# ----------------------------------------------------------------- formatters (rule commands)
def _fmt(v, nd=2):
    f = cb._f(v)
    return f"{f:.{nd}f}" if f is not None else "—"


def cmd_fear() -> str:
    fg = cb.get_fear_greed()
    i, u = fg["india"], fg["us"]
    return ("📊 Fear & Greed\n"
            f"🇮🇳 India: {_fmt(i['score'],0)} ({i['rating']} {i['trend']})\n"
            f"🇺🇸 US: {_fmt(u['score'],0)} ({u['rating']} {u['trend']})")


def cmd_top5() -> str:
    rows = cb.get_top_signals(5)
    if not rows:
        return "No scored signals available yet."
    lines = [f"{n}. {r['symbol']} ({_fmt(r['composite_score'],1)})"
             for n, r in enumerate(rows, 1)]
    return "🏆 Top 5 by composite score\n" + "\n".join(lines)


def cmd_macro() -> str:
    m = cb.get_macro_snapshot()
    fno, rates, fii = m["fno"], m["rates"], m["fii_dii"]
    lines = ["🌍 Macro snapshot"]
    if fno:
        lines.append(f"Nifty VIX {_fmt(fno['india_vix'])} | PCR {_fmt(fno['total_pcr'],3)}")
    repo = (rates.get("repo_rate") or {}).get("value")
    usdinr = (rates.get("usd_inr") or {}).get("value")
    cpi = (rates.get("cpi_inflation") or rates.get("wpi_inflation") or {}).get("value")
    lines.append(f"Repo {_fmt(repo,2)}% | USD/INR {_fmt(usdinr,2)}"
                 + (f" | Infl {_fmt(cpi,2)}%" if cpi is not None else ""))
    if fii:
        lines.append(f"FII {_fmt(fii['fii_net'],0)}Cr | DII {_fmt(fii['dii_net'],0)}Cr ({fii['date']})")
    return "\n".join(lines)


def cmd_alerts() -> str:
    alerts = cb.get_risk_alerts(10)
    if not alerts:
        return "✅ No active risk alerts."
    return "⚠️ Risk Alerts\n" + "\n".join(f"• {a}" for a in alerts)


def cmd_earnings() -> str:
    rows = cb.get_upcoming_earnings(14)
    if not rows:
        return "No earnings scheduled in the next 14 days."
    rows = sorted(rows, key=lambda r: r["results_date"])[:20]
    lines = [f"• {r['symbol']} — {r['results_date']:%d %b}"
             + (f" ({r['quarter']})" if r["quarter"] else "") for r in rows]
    return "📅 Earnings — next 14 days\n" + "\n".join(lines)


def cmd_news() -> str:
    rows = cb.get_top_news(10, days=2)
    if not rows:
        return "No scored news in the last couple of days."
    icon = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
    lines = [f"{icon.get(r['sentiment'],'⚪')} [{r['symbol']}] {r['headline'][:90]} "
             f"({_fmt(r['sentiment_score'],2)})" for r in rows]
    return "📰 Top news by sentiment\n" + "\n".join(lines)


def cmd_signal(arg: str) -> str:
    if not arg:
        return "Usage: /signal SBIN"
    d = cb.get_signal_detail(arg)
    if not d or not d["px"]:
        return f"No signal data for '{arg}'."
    px, sc, st = d["px"], d["score"] or {}, d["stock"]
    return (f"📈 {st['tradingsymbol']} — {st['name']}\n"
            f"Verdict: {d['verdict']}\n"
            f"Close: {_fmt(px['close'])} | RSI14: {_fmt(px['rsi_14'])}\n"
            f"MACD: {_fmt(px['macd'],3)} / sig {_fmt(px['macd_signal'],3)}\n"
            f"SMA50: {_fmt(px['sma_50'])} | SMA200: {_fmt(px['sma_200'])}\n"
            f"Composite score: {_fmt(sc.get('composite_score'),1)}")


def cmd_fundamentals(arg: str) -> str:
    if not arg:
        return "Usage: /fundamentals SBIN"
    d = cb.get_fundamentals(arg)
    if not d or not d["fundamentals"]:
        return f"No fundamentals for '{arg}'."
    f, st = d["fundamentals"], d["stock"]
    mcap = cb._f(f["market_cap"])
    mcap_s = f"{mcap/1e5:.2f}L Cr" if mcap else "—"
    return (f"📊 {st['tradingsymbol']} fundamentals\n"
            f"Mkt cap: ₹{mcap_s}\n"
            f"PE: {_fmt(f['pe_ratio'])} | PB: {_fmt(f['pb_ratio'])}\n"
            f"ROE: {_fmt(f['roe'])}% | ROCE: {_fmt(f['roce_pct'])}%\n"
            f"D/E: {_fmt(f['debt_to_equity'])} | Div yield: {_fmt(f['dividend_yield_pct'])}%\n"
            f"Promoter: {_fmt(f['promoter_holding_pct'])}% | Pledged: {_fmt(f['pledged_pct'])}%")


def cmd_insider(arg: str) -> str:
    if not arg:
        return "Usage: /insider SBIN"
    d = cb.get_insider(arg, days=90, limit=8)
    if not d or not d["trades"]:
        return f"No insider trades for '{arg}' in the last 90 days."
    st = d["stock"]
    lines = [f"• {t['date']:%d %b} {t['transaction']} {int(t['quantity']) if t['quantity'] else '?'} "
             f"@ {_fmt(t['price'])} ({t['person_category'] or '?'})" for t in d["trades"]]
    return f"🕵️ {st['tradingsymbol']} insider trades (90d)\n" + "\n".join(lines)


def cmd_watchlist() -> str:
    rows = cb.get_watchlist_scores()
    if not rows:
        return "Watchlist is empty or unscored."
    lines = [f"{r['symbol']}: {_fmt(r['composite_score'],1)}" for r in rows[:40]]
    return "👁️ Watchlist (by composite score)\n" + "\n".join(lines)


COMMANDS = {
    "start": lambda a: "👋 Welcome to your Stock Analyzer bot!\n\n" + COMMANDS_HELP,
    "help": lambda a: COMMANDS_HELP,
    "top5": lambda a: cmd_top5(),
    "fear": lambda a: cmd_fear(),
    "macro": lambda a: cmd_macro(),
    "alerts": lambda a: cmd_alerts(),
    "earnings": lambda a: cmd_earnings(),
    "news": lambda a: cmd_news(),
    "signal": cmd_signal,
    "fundamentals": cmd_fundamentals,
    "insider": cmd_insider,
    "watchlist": lambda a: cmd_watchlist(),
}


# ----------------------------------------------------------------- AI query (Gemini → Groq)
def _ask_gemini(context: str, question: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    body = {
        "system_instruction": {"parts": [{"text": AI_SYSTEM_PROMPT}]},
        "contents": [{"role": "user",
                      "parts": [{"text": f"DATA CONTEXT:\n{context}\n\nQUESTION: {question}"}]}],
        "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3},
    }
    try:
        r = requests.post(url, json=body, timeout=40)
        if r.status_code == 429:
            log.warning("Gemini quota exhausted (429) — falling back to Groq")
            return None
        if r.status_code != 200:
            log.warning(f"Gemini error {r.status_code}: {r.text[:200]}")
            return None
        cands = r.json().get("candidates", [])
        if not cands:
            return None
        return "".join(p.get("text", "") for p in cands[0]["content"]["parts"]).strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning(f"Gemini request failed: {e}")
        return None


def _ask_groq(context: str, question: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": GROQ_MODEL, "max_tokens": 800, "temperature": 0.3,
                  "messages": [
                      {"role": "system", "content": AI_SYSTEM_PROMPT},
                      {"role": "user",
                       "content": f"DATA CONTEXT:\n{context}\n\nQUESTION: {question}"}]},
            timeout=40)
        if r.status_code != 200:
            log.warning(f"Groq error {r.status_code}: {r.text[:200]}")
            return None
        return r.json()["choices"][0]["message"]["content"].strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning(f"Groq request failed: {e}")
        return None


def answer_ai_query(question: str) -> str:
    """Gemini → Groq → rule-based apology. Always returns a user-facing string."""
    context = cb.build_context(question)
    reply = _ask_gemini(context, question)
    engine = "Gemini"
    if reply is None:
        reply = _ask_groq(context, question)
        engine = "Groq"
    if reply is None:
        log_status(f"AI query fell through (no Gemini/Groq) for: {question[:80]}")
        return ("🤖 AI is temporarily unavailable. Here's what I have from the data:\n\n"
                + context + "\n\nTry a command like /top5, /macro or /signal SBIN.")
    log.info(f"AI answered via {engine}")
    return reply


# ----------------------------------------------------------------- daily digest
def build_daily_digest() -> str:
    fg = cb.get_fear_greed()
    i, u = fg["india"], fg["us"]
    top = cb.get_top_signals(5)
    alerts = cb.get_risk_alerts(5)
    fii = cb.get_fii_dii()
    earnings = sorted(cb.get_upcoming_earnings(7), key=lambda r: r["results_date"])[:6]
    news = cb.get_top_news(5, days=2)
    m = cb.get_macro_snapshot()
    fno, rates = m["fno"], m["rates"]

    lines = [f"☀️ Daily Digest — {datetime.now():%a %d %b %Y}", ""]
    lines.append(f"📊 Fear & Greed: India {_fmt(i['score'],0)} ({i['rating']} {i['trend']}) | "
                 f"US {_fmt(u['score'],0)} ({u['rating']} {u['trend']})")
    if top:
        lines.append("🏆 Top signals: " + ", ".join(
            f"{t['symbol']} ({_fmt(t['composite_score'],1)})" for t in top))
    if alerts:
        lines.append("⚠️ Risk: " + "; ".join(alerts))
    if fii:
        lines.append(f"💰 FII {_fmt(fii['fii_net'],0)}Cr | DII {_fmt(fii['dii_net'],0)}Cr")
    if earnings:
        lines.append("📅 Earnings: " + ", ".join(
            f"{e['symbol']} ({e['results_date']:%d %b})" for e in earnings))
    if news:
        icon = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
        lines.append("📰 News:")
        for n in news[:5]:
            lines.append(f"  {icon.get(n['sentiment'],'⚪')} [{n['symbol']}] "
                         f"{n['headline'][:80]} ({_fmt(n['sentiment_score'],2)})")
    macro_bits = []
    if fno:
        macro_bits.append(f"VIX {_fmt(fno['india_vix'])}")
        macro_bits.append(f"PCR {_fmt(fno['total_pcr'],3)}")
    repo = (rates.get("repo_rate") or {}).get("value")
    if repo is not None:
        macro_bits.append(f"Repo {_fmt(repo,2)}%")
    if macro_bits:
        lines.append("🌍 Macro: " + " | ".join(macro_bits))
    return "\n".join(lines)


def send_daily_digest() -> dict:
    """Build and push the morning digest. Called by the Dagster asset."""
    try:
        text = build_daily_digest()
    except Exception as e:  # noqa: BLE001
        log.error(f"Digest build failed: {e}", exc_info=True)
        log_status(f"Daily digest build failed: {e}")
        text = "☀️ Daily Digest unavailable — data build failed. Check the pipeline."
    ok = send_message(text)
    if not ok:
        log_status("Daily digest send failed (Telegram not configured or API error)")
    return {"sent": ok, "length": len(text)}


# ----------------------------------------------------------------- command routing
def handle_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()   # strip @botname in groups
        arg = parts[1].strip() if len(parts) > 1 else ""
        handler = COMMANDS.get(cmd)
        if handler:
            try:
                return handler(arg)
            except Exception as e:  # noqa: BLE001
                log.error(f"Command /{cmd} failed: {e}", exc_info=True)
                log_status(f"Command /{cmd} failed: {e}")
                return "Sorry, that command hit an error. Try /help."
        return f"Unknown command /{cmd}. Send /help for the list."
    # free text → AI
    try:
        return answer_ai_query(text)
    except Exception as e:  # noqa: BLE001
        log.error(f"AI query failed: {e}", exc_info=True)
        log_status(f"AI query failed: {e}")
        return "Sorry, I couldn't process that just now. Try /help for commands."


# ----------------------------------------------------------------- polling loop
def run_listener() -> None:
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_BOT_TOKEN missing in .env — cannot start listener.")
        return
    print(f"Telegram bot listening (Gemini={'on' if GEMINI_API_KEY else 'off'}, "
          f"Groq={'on' if GROQ_API_KEY else 'off'}).")
    offset = None
    allowed = str(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=40)
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg or "text" not in msg:
                    continue
                chat_id = str(msg["chat"]["id"])
                if allowed and chat_id != allowed:
                    log.info(f"Ignoring message from non-allowed chat {chat_id}")
                    continue
                reply = handle_text(msg["text"])
                send_message(reply, chat_id=chat_id)
        except requests.exceptions.RequestException as e:
            log.warning(f"getUpdates network error: {e}; retrying in 5s")
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            log.error(f"Listener loop error: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--digest" in sys.argv:
        print(build_daily_digest())
        if "--send" in sys.argv:
            print(send_daily_digest())
    elif "--context" in sys.argv:
        q = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "market overview"
        print(cb.build_context(q))
    else:
        run_listener()
