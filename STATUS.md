# Stock Analyzer — Status Log

## 2026-06-28

### Blocker Resolution

| Blocker | Status | Notes |
|---------|--------|-------|
| Dagster running | ✅ RESOLVED | `dagster dev -w workspace.yaml` started, UI at http://127.0.0.1:3000 |
| Kite TOTP auto-refresh | ⚠️ WAITING ON USER | `kite_auth/auto_login.py` exists, playwright+chromium ready. Missing from .env: `KITE_USERNAME`, `KITE_PASSWORD`, `KITE_TOTP_SECRET` |
| mfdata.in MF holdings | ❌ DEAD | `https://mfdata.in/api/v1/search?q=hdfc` times out (10s). Domain unreachable. MF holdings integration deferred — see TASKS.md |

### Tier 2 Macro — built this session (all on venv310, Python 3.10)

| Integration | Status | Rows | Source | Commit |
|-------------|--------|------|--------|--------|
| F&O expiry calendar | ✅ (pre-existing, verified) | 18 | Kite NFO | 9d7e35e |
| GDP + WPI | ✅ DONE | 112 | MoSPI MCP (fastmcp) | 3dd5dfb |
| RBI forex reserves + credit growth | ✅ DONE | 20 | RBI DBIE via Playwright | efde7e0 |

- GDP growth Q2 FY26 = 8.23%; WPI inflation Mar-26 = 3.88%
- Forex reserves total = $672.6B; bank credit growth +17.65% YoY (31-May-26)
- All three wired into `nse_macro_indicators` Dagster asset (nse_weekly group)
- No rate limits hit this session.

### Docker rebuild — ✅ DONE
- `docker compose up --build` completed (exit 0). All 4 containers up: dagster_user_code,
  dagster_webserver, dagster_daemon, dagster_db.
- Image now python:3.10.20. Verified inside container: fastmcp 3.4.2, openpyxl 3.1.5, playwright,
  OpenSSL all import; Dagster code server loaded repository.py with no errors; all three macro
  collectors import OK. The macro collectors now run inside the Dagster Docker stack.

### Next Actions
- Kite TOTP auto-refresh: `.env` now has KITE_USERNAME/PASSWORD/TOTP_SECRET (loaded by container) —
  verify `kite_auth/auto_login.py` end-to-end next session.
- Next Tier 2 item: RBI monetary policy calendar (manual seed)

### Data quality audit — nse_daily @ 2026-06-28 12:55
- gaps: {'ohlcv': 94, 'indicators': 0, 'signals': 0, 'news': 82} (total 176)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_weekly @ 2026-06-28 12:55
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_daily @ 2026-06-28 13:24
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 0, 'news': 82} (total 82)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_weekly @ 2026-06-28 13:24
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-06-28 19:42
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Data quality audit — nse_weekly @ 2026-06-28 14:45
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_daily @ 2026-06-28 14:45
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 0, 'news': 79} (total 79)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-06-28 20:12
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-28 20:43
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-28 21:13
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

- [telegram_bot 2026-06-28 23:30] AI query fell through (no Gemini/Groq) for: Why is SBIN looking strong?

### Session H — Telegram bot (2026-06-28)
- Built `data_collectors/context_builder.py` (DB data layer + AI context builder) and
  `data_collectors/telegram_bot.py` (rule commands + Gemini→Groq AI fallback + daily digest).
- Dagster: `telegram_daily_digest` asset (notifications group) → `telegram_digest_job` →
  `telegram_digest_daily` schedule at 08:00 IST. Definitions validate (35 assets, 13 jobs, 10 schedules).
- All rule commands + the digest verified against the live DB (no API keys needed for those).
- AI graceful fallback (no keys) verified — returns the compact data context + an apology.
- ⚠️ WAITING ON USER: `.env` needs TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (digest + commands),
  and GEMINI_API_KEY / GROQ_API_KEY (AI queries). End-to-end Telegram send/receive can only be
  verified once these are added. See ENGINEERING.md "Telegram bot" + .env.example for how to obtain them.
### Watchdog retry — 2026-06-29 01:57
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Data quality audit — nse_daily @ 2026-06-29 01:57
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 67} (total 161)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-06-29 02:28
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 03:13
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 03:47
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 04:17
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 04:59
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 05:45
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 06:16
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Data quality audit — nse_daily @ 2026-06-29 06:44
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 66} (total 160)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-06-29 09:31
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 10:05
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 10:48
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 11:22
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Watchdog retry — 2026-06-29 12:09
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 12:51
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 13:28
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 14:07
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 14:47
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 15:33
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 16:11
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 16:55
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 17:26
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 18:08
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 18:39
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 19:19
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 19:56
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 20:30
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 21:14
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 22:00
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 22:34
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-29 23:17
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 00:02
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 00:36
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 01:17
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 02:03
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 02:34
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 03:04
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 03:37
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 04:21
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 05:07
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 05:42
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 06:24
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 07:07
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 07:40
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 08:24
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 09:10
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 09:43
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 10:27
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 11:13
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 11:47
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 12:20
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 12:58
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 13:35
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 14:13
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 14:47
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 15:19
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 15:59
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 16:30
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 17:01
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 17:43
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 18:22
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 18:54
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 19:37
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 21:07
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 21:37
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 22:07
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 22:45
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 23:16
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-06-30 23:50
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 00:28
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 01:01
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 01:33
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 02:08
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 02:46
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 03:18
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 03:53
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 04:33
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-01 05:05
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) sec_form4, us_prices

### Watchdog retry — 2026-07-02 00:34
  - nse_fno_job: stale source(s) fno_data
  - nse_daily_job: stale source(s) block_deals, news_sentiment, kite_quotes, kite_ohlcv, tech_indicators, signals, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices

### Data quality audit — nse_daily @ 2026-07-02 00:34
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 58} (total 152)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_daily @ 2026-07-02 00:34
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 58} (total 152)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_weekly @ 2026-07-02 00:34
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-07-02 00:36
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals
  - us_daily_job: stale source(s) us_prices

### Data quality audit — nse_daily @ 2026-07-02 00:36
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 58} (total 152)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

## 2026-07-02 — Session K: India/US demarcation + FII/DII trend + US watchlist + volume indicators

### Volume indicators (migration 0022)
- Added technical_indicators.volume_sma_20, volume_ratio, volume_trend, obv, vwap
- Added stock_scores.volume_signal (VOLUME_BREAKOUT / VOLUME_BREAKDOWN / LOW_VOLUME_MOVE)
- analysis/calculate_indicators.py computes all volume indicators; volume_signal upserts onto
  the stock's latest score row. Backfilled 94 NSE + all US watchlist stocks (full ~2yr history).

### FII/DII day-over-day trend
- niftytrader webapi added as a 30-day history source (NSE API only returns the latest day).
  fii_dii_collector now backfills the 30-day window on every run. fii_dii_flows: 4 -> 30 rows.
- GET /api/macro/fii-dii-trend — 30d series + 5d/10d MAs + 5d/10d cumulative + buy/sell streaks
  + today-vs-yesterday. Rendered on Macro page (green/red bars, MA overlays, summary stats).
- FII selling-streak >=3 already surfaces as a Risk Alert.

### US watchlist add (MELI etc.)
- webapp/backend/us_stock_add.py: Polygon reference/tickers typeahead + add flow
  (insert stock, fetch 2yr OHLCV, compute indicators, add to watchlist). Endpoints:
  GET /api/watchlist/search-us, POST /api/watchlist/add-us. Verified MELI (501 bars, 482 ind).
- Watchlist page searches NSE + US simultaneously with market badges.

### India/US demarcation
- Signals/Dashboard: market filter (India default / US / All), Market badge column, Volume (x avg)
  column; dashboard endpoint now includes US stocks + volume + volume_signal + exchange.
- Macro: separate 🇮🇳 India and 🇺🇸 US sections (US = FRED). FII/DII trend under India.
- Opportunities: market filter + badges (exchange added to endpoint).
- Stock detail: VWAP line on price chart, colour-coded volume bars + 20d avg overlay, OBV panel.
- Raw data tables: exchange/market columns render as flag badges.
- Smart Money (tabs), Risk Alerts (badges+filter), Fear&Greed (labels) already demarcated.

### Watchdog retry — 2026-07-02 01:06
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Data quality audit — nse_daily @ 2026-07-02 01:20
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 58} (total 152)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Data quality audit — nse_weekly @ 2026-07-02 01:20
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 4 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60), CUB(75)

### Watchdog retry — 2026-07-02 01:36
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

## 2026-07-02 — Session K part 2: Private Portfolio (localhost-only, TOTP, encrypted)
- Migration 0023: `portfolio` schema + holdings (sensitive cols BYTEA via pgcrypto) + audit_log.
- Role `portfolio_user` (schema-scoped + read-only market data); `stock_reader` denied portfolio schema.
- Access gate (all 3 required): localhost-only (blocks ngrok via forwarding-header check) +
  main session + 15-min TOTP session (PORTFOLIO_TOTP_SECRET). Encryption key in .env only.
- Endpoints: verify-totp, status, preview, save, holdings, holding PUT/DELETE, summary, alerts,
  signal-overlay. P&L/current value computed live, NEVER stored. Not in /api/data/* allowlist.
- Frontend Portfolio.tsx (TOTP gate, drag/drop upload+preview, dashboard, 15-min countdown);
  Signals dashboard shows 💼 + vs-stop/target for held stocks (localhost+TOTP overlay).
- Telegram alerts: type + direction only (no qty/price/P&L).
- Verified: ngrok→403, no-TOTP→401, wrong code→401+audit, encrypted at rest (no plaintext),
  stock_reader denied, portfolio absent from /api/data/*, no financials in logs.
- .env additions: PORTFOLIO_TOTP_SECRET, PORTFOLIO_ENCRYPTION_KEY, PORTFOLIO_DATABASE_URL.
- Docker daemon down this session (webapp runs on host launchd; no rebuild needed).

## 2026-07-02 — Session L: 4-pillar explainable signal engine
- Migration 0024: signal_explanations (per stock/date/horizon: 4 pillar scores + reasoning
  JSON, overall, confidence, all_pillars_agree, contrary, what_would_change, cached external
  sentiment) + advisor_opinions placeholder.
- signals/ package: technical, fundamental, flows, external (DDG+GoogleNews+VADER, 6h cache),
  advisor (placeholder), combiner (per-horizon reweight), engine (orchestrate + persist).
- nse_signals Dagster asset now runs the engine (dep on news_sentiment).
- Backfill: 98 stocks × 3 horizons = 294 rows. Avg pillars T50.8 F60.7 FL49.9 E57.7.
  External fetched+cached for all 98. Coverage: technical/flow 100%, fundamental/external
  lower only for ETFs/small-caps that lack the underlying data (surfaced honestly).
- UI: /signal-engine (🎯) — 3 horizon tabs, pillar badges, all-pillars-agree filter,
  slide-in explanation panel (4 pillars + contrary + what-would-change + advisor coming-soon).
- Legacy generate_signals.py documented in ENGINEERING ("Signal Generation — Legacy").
- Installed deps: duckduckgo-search, vaderSentiment.

### Watchdog retry — 2026-07-02 02:06
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

## 2026-07-02 — Session L.1: macro vs stock-specific separation in flows pillar
- signals/flows.py split: compute_macro_flows (FII/DII 5d+streak, India Fear&Greed, VIX, PCR,
  Nifty breadth %>SMA50; cached per day) + compute_stock_flows (insider, bulk, SAST, 13F,
  FII%/DII% QoQ, MF MoM, analyst target/upside, news, Google Trends). Reasoning prefixed
  [MACRO]/[STOCK]. Analyst + FII%/DII trend moved out of fundamental → flows (no double-count).
- New GET /api/signals/market-context (macro inputs used in ALL signals today).
- Signal Engine panel: flows shown as 🌍 Market Context + 🎯 Stock-Specific sub-sections.
- Macro page: "📊 Current Market Context for Signal Engine" card.
- Recomputed 98 stocks × 3 horizons (external all cached; avg F62.7 FL48.2). SBIN verified:
  6 [MACRO] + 5 [STOCK] flow lines.

### Data quality audit — nse_daily @ 2026-07-02 02:16
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 57} (total 151)
- 3 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60)

### Data quality audit — nse_weekly @ 2026-07-02 02:29
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 3 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60)

### Watchdog retry — 2026-07-02 02:36
  - nse_daily_job: stale source(s) kite_quotes, kite_ohlcv, tech_indicators, signals

### Data quality audit — nse_daily @ 2026-07-02 02:37
- gaps: {'ohlcv': 0, 'indicators': 0, 'signals': 94, 'news': 56} (total 150)
- 3 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60)

### Data quality audit — nse_weekly @ 2026-07-02 02:50
- gaps: {'fundamentals': 4, 'shareholding': 3} (total 7)
- 3 stock(s) below 80% completeness: PHARMABEES(60), NIFTYBEES(60), ITBEES(60)

### Watchdog retry — 2026-07-02 03:20
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-02 03:50
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-02 04:20
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-02 04:53
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-02 07:08
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-02 07:59
  - nse_daily_job: stale source(s) kite_quotes

### Watchdog retry — 2026-07-04 22:35
  - nse_daily_job: stale source(s) news_sentiment, block_deals, kite_quotes, fii_dii
  - us_daily_job: stale source(s) sec_form4, us_prices
  - nse_fno_job: stale source(s) fno_data

### Watchdog retry — 2026-07-04 23:05
  - nse_daily_job: stale source(s) nse_quotes
