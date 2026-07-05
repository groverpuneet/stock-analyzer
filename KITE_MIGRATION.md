# Kite → Free-Source Migration Note

**Goal:** remove the Zerodha Kite Connect integration from the codebase entirely, because a
Kite access token is a **full-account trading credential** (Kite has no read-only token/scope),
and the stored `KITE_PASSWORD` / `KITE_TOTP_SECRET` / `KITE_API_SECRET` in `.env` let anyone
mint one. Since this system is an **EOD / post-market analysis pipeline** (it reads
`daily_prices`, not live ticks), it does not actually need a broker. This note documents
**every piece of data we currently pull from Kite**, **what consumes it**, and the **free,
non-brokerage source** that replaces each — verified empirically against the live DB.

_Status legend:_ ✅ verified (bit-exact / confirmed) · 🔍 verifying · ⚠️ gap/needs care

---

## 1. What data we get from Kite today (complete call-site inventory)

| Kite call | Files (call sites) | Data provided | Consumed by |
|---|---|---|---|
| `historical_data()` | `collect_watchlist_data.py:117`, `backfill_watchlist_prices.py:84`, `full_history_backfill.py:58,63`, `kite_collector.py:96` | Daily OHLCV bars (open/high/low/close/volume) | `daily_prices` table → **everything** (indicators, signals) |
| `quote()` | `collect_watchlist_data.py:133` | Post-close quote snapshot (LTP + buy/sell qty, OI, circuit limits) | `quotes` table (post-close snapshot) |
| `ltp()` | `dagster/assets/nse_daily.py:22` | Last traded price of RELIANCE | **Token-validity probe only** (guards `nse_raw_prices`) |
| `instruments("NSE")` | `manage_watchlist.py:30`, `expand_stock_universe.py:49`, `kite_collector.py:78`, `scripts/add_watchlist_stocks.py:53` | NSE equity symbol master (tradingsymbol, instrument_token, ISIN, name) | `stocks` table; watchlist mgmt; universe expansion |
| `instruments("NFO")` | `expiry_calendar_collector.py:49` | F&O contract master (expiry date, FUT/CE/PE type, underlying) | `expiry_calendar` table |
| `mf_instruments()` | `scripts/add_mf_watchlist.py:5,97` | Mutual-fund scheme list (ISIN → scheme) | MF watchlist rows (`INF…` ISINs) |
| `login_url()`, `generate_session()`, `set_access_token()` | `kite_auth/auto_login.py`, `kite_test.py`, all collectors | Daily auth / token exchange | The entire token machinery |

**Exploration-only / throwaway:** `data_collectors/explore_all_kite_data.py`, `data_collectors/kite_test.py` (dev scripts, safe to delete).

---

## 2. Data requirements → free replacement

| Data need | Current (Kite) | Free replacement | Parity / status |
|---|---|---|---|
| **Daily OHLCV** (backbone) | `historical_data` | **NSE bhavcopy** (whole-market EOD CSV, 1 file/day) as daily driver **+ yfinance** (`SYMBOL.NS`) for 2-yr history & gap-fill | ✅ **Bit-exact** — 0.00 diff on O/H/L/C + volume vs current `daily_prices`; 93/93 NSE watchlist symbols in bhavcopy; yfinance 20/20 incl. renamed tickers |
| **Post-close quote** | `quote` | bhavcopy `ClsPric`/`LastPric` (or yfinance last bar) | ✅ Core price covered. ⚠️ Extra fields (buy/sell qty, OI, circuit limits) have no free equivalent — but **nothing downstream reads them** (signals read `daily_prices`); `quotes` snapshot degrades gracefully |
| **Token-validity probe** | `ltp` | — (delete) | ✅ No token → no probe needed |
| **NSE symbol master** | `instruments("NSE")` | **bhavcopy** columns (`TckrSymb`, `ISIN`, `FinInstrmNm`, `SctySrs`) — 2,384 EQ symbols | ✅ verified. ⚠️ `instrument_token` is NOT-NULL/UNIQUE in `stocks`; new stocks need a synthetic token (e.g. crc32(ISIN)); existing rows keep theirs |
| **F&O expiry calendar** | `instruments("NFO")` | **NSE UDiFF F&O bhavcopy** archive ZIP (direct URL — see below) | ✅ verified — 33,211 rows for 2026-07-03, 18 distinct expiries reproduced with correct symbol_count/has_futures. ⚠️ jugaad-data `bhavcopy_fo_raw` is BROKEN (dead pre-2024 URL) — fetch UDiFF directly |
| **MF NAV / scheme list** | `mf_instruments` | **AMFI `NAVAll.txt`** (free static, ISIN-keyed) | ✅ verified — **18/18** watchlist MF ISINs resolve with NAV + date |
| **Daily auth (token)** | `login_url`/`generate_session`/TOTP | — (delete entirely) | ✅ Free sources need no auth |

**Already non-Kite (unaffected):** US prices (Polygon), US/India macro (FRED, RBI DBIE, MoSPI),
news (RSS+FinBERT), fundamentals (Screener), FII/DII, insider (SEC/NSE), 13F, etc.

---

## 3. Infrastructure to delete on removal

- **Files:** `kite_auth/` (auto_login.py, readonly_kite.py), `data_collectors/kite_collector.py`,
  `data_collectors/explore_all_kite_data.py`, `data_collectors/kite_test.py`, `.kite_access_token`.
- **Dagster:** `assets/kite_infra.py` (`kite_token_refreshed`), `kite_token_job`,
  `kite_token_schedule` + `kite_token_retry_schedule` (schedules.py), the `deps=["kite_token_refreshed"]`
  + `kite.ltp` guard in `nse_raw_prices`, and `kite_ohlcv`/`kite_quotes` keys in `sensors.py` SOURCE_JOB.
- **Config:** `.env` `KITE_*` vars (5); `requirements.txt` `kiteconnect` (add `yfinance`, `jugaad-data`).
- **External:** revoke the Kite Connect app in the Zerodha developer console; **rotate the Zerodha
  password + reset TOTP/2FA** (they were plaintext in `.env` → treat as exposed).

---

## 4. Migration plan (proposed order)

1. **New collectors** (additive, no removal yet): `nse_bhavcopy_collector.py` (daily OHLCV + symbol
   master), keep yfinance for history/gap-fill + a fallback; `amfi_nav_collector.py` (MF NAV);
   repoint `expiry_calendar_collector.py` to F&O bhavcopy.
2. **Rewire** `collect_watchlist_data.py` (`collect_data`) to bhavcopy; drop the `quote()` path (or
   fill `quotes` from bhavcopy). Swap backfill scripts to yfinance.
3. **Dagster:** drop `nse_raw_prices` token dep + `ltp` guard; delete kite_infra asset/job/schedules;
   fix SOURCE_JOB keys. Schedule note: bhavcopy publishes ~T+18:30 IST → either bump `nse_daily`
   from 16:00 to ~18:30 IST, or use yfinance for the 16:00 run.
4. **Symbol/universe scripts** (`manage_watchlist.py`, `expand_stock_universe.py`,
   `add_watchlist_stocks.py`, `add_mf_watchlist.py`) → bhavcopy symbol master / AMFI.
5. **Delete** all Kite files/config; revoke app; rotate creds.
6. **Verify:** run a full `nse_daily` + a backfill; diff new `daily_prices` rows vs the pre-migration
   values (must stay bit-exact); confirm indicators/signals recompute unchanged.

**Effort:** ~2–3 focused days. **Risk:** low–moderate (bhavcopy timing/UDiFF column layout, synthetic
`instrument_token` for new symbols, yfinance being unofficial → keep bhavcopy primary).

---

## 5. Verified source details (for the collectors)

**Equity + symbol master — NSE bhavcopy (UDiFF):**
`https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip`
(browser User-Agent, no cookies). Columns incl. `TckrSymb, ISIN, FinInstrmNm, SctySrs, OpnPric,
HghPric, LwPric, ClsPric, LastPric, TtlTradgVol`. History/gap-fill via yfinance `SYMBOL.NS`
(`auto_adjust=False` → raw Close to match current `daily_prices`).

**F&O expiries — UDiFF FO bhavcopy (jugaad's `bhavcopy_fo_raw` is broken, use this URL):**
`https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`
Map: expiry=`XpryDt`; type = `FUT` if `FinInstrmTp∈{STF,IDF}` else `OptnTp` (CE/PE); underlying=`TckrSymb`.
Existing `_classify()` + aggregation in `expiry_calendar_collector.py` work unchanged. Source tag `nse_fo_udiff`.
Walk back a few weekdays if the latest date 404s (holiday/not-yet-published ~T+18:30 IST).

**MF NAV — AMFI:** `https://www.amfiindia.com/spages/NAVAll.txt` (semicolon-delimited, grouped by AMC).
Data lines have 6 fields; ISIN is in **both** col 1 (growth/payout) and col 2 (reinvestment) — match either.
NAV=col 4, date=col 5 (`%d-%b-%Y`). Skip lines with <6 `;`-fields (headers/blanks). Watchlist MF ISINs
live in `stocks.tradingsymbol` where `instrument_type='MF'`; only MF table is `mf_stock_holdings`.

## 6. Remaining decision

- Move `nse_daily` schedule 16:00 → ~18:30 IST (bhavcopy publish time), OR keep 16:00 using yfinance
  for that run and let bhavcopy reconcile later. **Recommend:** bump to ~18:30 IST for authoritative EOD.

_This note is the pre-work for removing Kite. **All sources verified — nothing deleted yet;
awaiting go-ahead to execute the section-4 plan.**_
