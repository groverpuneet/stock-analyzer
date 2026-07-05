# Market-Data Provider Research — Stock Analyzer

**Scope:** India (NSE/BSE equities) **primary** + US equities. Ranked by **data quality vs cost**.
**Hard constraint:** NO brokerage-trading APIs. A data source must not require trading-account credentials that can place orders (Zerodha Kite was removed for exactly this reason).
**Compiled:** 2026-07-04. All pricing/limits are "as of 2026-07 fetch" — **pricing changes often; re-verify at the cited URL before committing budget.** FX used: **~₹85/USD** (approximate, not a live rate).

Items I could not verify at the source are marked **[UNVERIFIED]**. No pricing was invented.

---

## 0. TL;DR

- **EODHD (eodhd.com) is the single best-value clean API** for this system. It is the only mainstream global provider with *verified* NSE **and** BSE coverage for EOD OHLCV, intraday (1m/5m), fundamentals, corporate actions, and a symbol master — in one API, at retail prices ($19.99–$99.99/mo, verified).
- **India true real-time intraday is the one gap money can't cheaply close without a broker.** The only *compliant* (non-brokerage, exchange-licensed) real-time path is **TrueData** or **Global Datafeeds (GFDL)** — ~$17–$75/segment/mo — and even those give 1-second snapshots, not tick/full-depth. Everything cheaper is EOD or ~1–3 min delayed.
- **Three India data types have NO clean non-brokerage API anywhere** and require you to keep scraping/parsing official files: (a) **stock-level mutual-fund holdings**, (b) **insider / bulk-block deals / shareholding patterns**, (c) **F&O contract master** (strikes/expiries).
- **US is easy and mostly free:** SEC EDGAR covers insider (Form 4) + 13F at $0; cheap vendors cover the rest.
- **Keep** your current free India spine (NSE/BSE bhavcopy, AMFI). **Upgrade** fundamentals (Screener.in scraping → EODHD API) and, if budget allows, add TrueData for India intraday/F&O.

---

## 1. The 9 data types × top providers matrix

Grades are **A–D** (A = deep/accurate/well-documented; D = nominal/absent/fragile). "IN" = India (NSE/BSE), "US" = US equities. Cost bucket is the tier you'd actually need for *this* data type.

| Data type | EODHD | yfinance | FMP | Finnhub | Twelve Data | Alpha Vantage | Tiingo | Polygon | TrueData / GFDL (IN) | Free official (NSE/BSE/AMFI/SEC) |
|---|---|---|---|---|---|---|---|---|---|---|
| **1. EOD OHLCV** | IN **A** / US **A** — $19.99 | IN **B** / US **B** — free | IN **C** (NS only) / US **A** — $22 | US **A** paid / IN enterprise **D** | IN **B** / US **A** — free/$79 | US **B** / IN **D** stale — free | US **A** / IN **D** none — $30 | US **A** / IN **D** none — $29 | IN **A** (10yr) — $17+ | IN **A** bhavcopy / US **A** — free |
| **2. Intraday / real-time (esp. IN)** | IN **B** delayed 1m/5m — $29.99 / US **B** | IN **C** delayed / US **C** — free | US **B** RT / IN **D** — $59 | US **A** RT / IN enterprise **D** | US **B** / IN **D** EOD-only — $79 | US **B** / IN **D** — $49.99 | US **B** (IEX) / IN **D** — $30 | US **A** / IN **D** none — $79 | **IN A** 1-sec RT, no broker — $17–75/seg | IN **C** (~3-min delayed `/api`, fragile) — free |
| **3. Fundamentals** | IN **A** / US **A** — $59.99 | IN **C** / US **B** — free | IN **C** / US **A** — $22–149 | IN **C** paid / US **A** — ~$50/mkt | IN **C** [UNVERIFIED depth] / US **B** — free/$79 | IN **D** / US **B** — $49.99 | IN **D** / US **B** — $30 | US **B** / IN **D** — $79 | IN **B** partial (TrueData) — incl. | IN **B** Screener.in export (no API) / US **A** SEC — free |
| **4. Corp actions + earnings cal** | IN **B** div/split / US **A** — $19.99 | IN **B** div/split / US **B** — free | IN **C** ($149) / US **A** | US **A** paid / IN **C** | IN **B** / US **A** — free/$79 | US **B** / IN **D** | US **C** (no earn cal) / IN **D** | US **B** / IN **D** | IN **B** (TrueData corp data) | IN **A** NSE/BSE corp-actions CSV / US **A** — free |
| **5. F&O / option chain (IN)** | **D** (US options only) | **D** (US options only) | **D** | **D** (US only) | **D** (none) | **D** (US only) | **D** | **D** (US only) | **IN A** RT chain+Greeks+OI — $17–75/seg | IN **B** NSE EOD F&O + delayed chain (fragile) — free |
| **6. MF NAV + stock-level holdings (IN)** | NAV **C** [UNVERIFIED] / holdings **D** | **D** | **D** | **D** | US MF **C** / IN **D** | **D** | US MF-NAV **C** / IN **D** | **D** | **D** | **NAV A** AMFI free; **holdings D** (per-AMC PDF/XLS only — GAP) |
| **7. News + sentiment** | **B** global engine, IN mapping [UNVERIFIED] — $99.99 | **C** headlines, no sentiment — free | US **B** / IN **D** | **IN B** (NSE, confirmed) / US **A** — paid | **D** (no news endpoint) | US **B** / IN **D** thin — $49.99 | US **B** news, no sentiment / IN **D** — $30 | US **B** / IN **D** | **D** | IN **C** RSS (section-level) — free |
| **8. Insider / bulk-block / shareholding / 13F** | US **B** (13F/insider) / IN **D** — $59+ | US **B** (SEC) / IN **D** — free | US **A** (13F+insider, $149) / IN **D** | US **A** + **IN insider named B** / IN block **D** — paid | US **B** (SEC) / IN **D** | US **B** / IN **D** | **D** | US **D** (none) | **D** | **US A** SEC EDGAR free; **IN C** NSE/BSE scrape (bulk/block, SHP), fragile — free |
| **9. Symbol / instrument master** | IN **A** (NSE+BSE+ISIN) / US **A** — $19.99 | IN **C** / US **C** — free | IN **C** / US **A** | IN **B** / US **A** paid | IN **A** (XNSE/XBOM) / US **A** — free | IN **D** / US **B** | US **A** / IN **D** — $30 | US **A** / IN **D** | IN **A** (equity+F&O master) — incl. | **IN A** NSE `EQUITY_L.csv` + BSE scrip master (+ISIN) / free; **F&O master GAP** |

**Reading the matrix:** For India single-stock data, the realistic columns are **EODHD (paid, best breadth)**, **free official files (NSE/BSE/AMFI, EOD only)**, and **TrueData/GFDL (paid, the only compliant real-time)**. Every US-centric column (Tiingo, Polygon, Alpha Vantage, FMP, Finnhub standard, Twelve Data) is thin-to-empty for India beyond, at most, EOD.

---

## 2. Recommended stack — best pick per data type at $0 and ~$50/mo

Optimized for **quality-per-rupee**, **no brokerage credentials**. "$50/mo budget" is a total soft cap for a personal project; you cannot buy everything — spend it where it moves the needle (fundamentals + India intraday).

| # | Data type | **$0 budget pick** | **~$50/mo pick** | Runner-up / why |
|---|---|---|---|---|
| 1 | **EOD OHLCV (IN+US)** | NSE/BSE bhavcopy (IN) + Stooq/yfinance (US) | **EODHD All-World $19.99** (IN NSE+BSE + US, adjusted, symbol master) | yfinance (free but unofficial/fragile); Twelve Data free (US strong, IN EOD-only) |
| 2 | **Intraday / real-time (IN = the gap)** | NSE `/api` ~3-min delayed (fragile) or yfinance delayed | **TrueData Velocity** (~₹1,440–2,796/seg ≈ $17–33/seg) — 1-sec RT, **no broker** | GFDL (~$44/seg); EODHD Extended $29.99 (delayed 1m/5m, not RT) |
| 3 | **Fundamentals (IN+US)** | Screener.in Excel export (IN, manual) + SEC EDGAR (US) | **EODHD Fundamentals $59.99** (NSE+BSE+US via clean API) — *slightly over $50; the one worth it* | FMP Premium $59 (US A, IN thin); Finnhub (~$50/mkt, US strong) |
| 4 | **Corp actions + earnings cal** | NSE/BSE corp-actions CSV (IN) + EODHD-free/US vendors | **EODHD $19.99** (IN div/split + US) — reconcile bonus/rights vs free NSE/BSE | FMP ($149 for full IN); *no vendor is reliable for IN earnings dates — supplement from NSE* |
| 5 | **F&O / option chain (IN)** | NSE EOD F&O bhavcopy + NSE delayed option-chain `/api` (fragile) | **TrueData / GFDL** (RT chain + Greeks + OI, no broker) — same seg sub as #2 | Sensibull web (~1-min delayed, Google login only, **no API** — manual) |
| 6 | **MF NAV + stock-level holdings (IN)** | **AMFI `NAVAll.txt`** (NAV, free, canonical) + mfapi.in wrapper | Same (NAV is a solved free problem) — **holdings still a GAP** (see §3) | mfdata.in (free, no-SLA, has rare reverse "which funds own stock X"); Tickertape Pro CSV (no API) |
| 7 | **News + sentiment (IN+US)** | RSS (Moneycontrol/ET/Mint) + FinBERT (your current stack) | **Finnhub** (confirmed NSE company news + sentiment, paid) | Alpha Vantage NEWS_SENTIMENT (US good, IN thin); EODHD news $99.99 (IN mapping [UNVERIFIED]) |
| 8 | **Insider / bulk-block / 13F** | **SEC EDGAR** (US insider+13F, free) + NSE/BSE scrape (IN bulk/block, SHP) | Same free stack; optionally **Finnhub** (IN insider *named*, paid) for a clean IN insider feed | FMP Ultimate $149 (US 13F+insider); no clean IN block-deal API exists |
| 9 | **Symbol / instrument master** | **NSE `EQUITY_L.csv` + BSE scrip master** (free, incl. ISIN) + SEC | **EODHD exchange-symbol-list** (turnkey NSE/BSE + ISIN) bundled w/ #1 | Twelve Data (free, IN symbol catalogs); **F&O master has no free non-broker source — parse F&O bhavcopy** |

### Concrete "~$50/mo" build (compliant)
- **EODHD All-World Extended $29.99** → IN+US EOD **+ intraday(1m/5m delayed)** + corp actions + symbol master + fundamentals-lite. *(Or All-World $19.99 if you don't need vendor intraday.)*
- **AMFI + SEC EDGAR + NSE/BSE files** → $0 for MF NAV, US filings, IN bulk/block/shareholding, F&O EOD.
- **Keep RSS+FinBERT** → $0 news/sentiment.
- **Total ≈ $30/mo**, leaving ~$20 headroom. **Spend the rest** on either (a) **EODHD Fundamentals $59.99** if clean IN+US statements matter more than real-time, **or** (b) **one TrueData segment (~$17–33)** if you need compliant India real-time/F&O. You cannot comfortably fit both in $50 — pick per your priority (fundamentals vs live intraday).

---

## 3. The honest gaps (no good non-brokerage source)

### Gap A — India TRUE real-time intraday & tick/full-depth
- **No free source.** NSE's website `/api/*` (e.g. `option-chain-indices`) is ~3-min delayed [delay UNVERIFIED], undocumented, anti-bot protected (403/CAPTCHA at ~3–4 hits/min), and **its ToS explicitly prohibits automated scraping** — unfit for production.
- **Least-bad compliant option:** **TrueData** or **Global Datafeeds** — exchange-*authorized* vendors that license NSE/BSE/MCX directly, so **no trading account is required** (rule-compliant). But: only **1-second snapshots** (not true tick / not full order-book depth), ~$17–75/segment/mo **plus separate exchange fees** [exact fees UNVERIFIED], redistribution prohibited. TrueData is the better personal-project pick (published pricing, official Python libs, longer intraday history).
- **The brokerage tradeoff (spelled out — why the rule exists):** The cheapest/best real-time + tick + option-chain-with-Greeks data comes from **broker APIs** — several give data *for free* (Upstox, Angel One SmartAPI, Fyers, ICICI Breeze, 5paisa) or cheaply (**Kite ₹500/mo** — note: *not* ₹2000 anymore, dropped Feb 2025; **Dhan data ₹499/mo**). **Disqualifier:** in all of them the token that streams data is the *same authenticated trading session* that can **place/modify/cancel orders and touch funds** (Angel One and Dhan document 20 orders/sec on that session). There is no read-only scope.
  - **The single exception worth knowing:** **Upstox's "Analytics Token"** is a 1-year, strictly **read-only, GET-only** credential that *cannot* place/modify orders and is generated without an OAuth trading redirect. It still requires a funded Upstox account to *exist*, so it does **not** satisfy a strict "no trading account at all" reading — but it removes the order-placement capability from the credential in use. If the rule is ever softened to "no *order-capable* credential," this is the least-bad, and it's free. **read-only ≠ no-account — flag for the security owner.**

### Gap B — India stock-level mutual-fund holdings
- **NAV is solved & free** (AMFI `NAVAll.txt`). **Holdings is not.** There is **no official structured/aggregated holdings API** from AMFI or SEBI. Ground truth = SEBI-mandated **monthly** portfolio disclosures published as **Excel/PDF across ~40+ AMC websites**, **~T+10 lag, monthly granularity** (intra-month trades invisible). Hub: `amfiindia.com/online-center/portfolio-disclosure`.
- **Least-bad options:** **mfdata.in** (free community API; uniquely offers reverse lookup "which funds hold stock X" via `/api/v1/stocks/{name}/holders`; **no SLA/ToS**, fields [UNVERIFIED]); **Tickertape Pro** (~₹2,399/yr) can CSV-export funds-holding-a-stock but **no API**; **Morningstar India/Direct** is the only genuinely licensed structured-holdings API — **enterprise, expensive [UNVERIFIED]**. For a personal build: parse AMFI/AMC monthly disclosures yourself, or accept mfdata.in's no-SLA risk.

### Gap C — India insider / bulk-block deals / shareholding patterns
- **US is free** (SEC EDGAR: Form 4 insider since 2001, 13F datasets since ~2013; constraint: 10 req/s + descriptive User-Agent or 403).
- **India has no official public developer API.** Data lives as HTML + undocumented website JSON + CSV/PDF. Practical access = scraping NSE (`/api/historicalOR/bulk-block-short-deals`, `corporate-share-holdings-master`) / BSE pages — **against NSE ToS, fragile, anti-bot**. Trendlyne/Tickertape aggregate all of it but expose **no sanctioned API**. The only clean *licensed* India insider feed found is **Finnhub** (India insider explicitly named, paid) — but it does not cover Indian bulk/block deals or SEBI shareholding patterns.

### Gap D — India F&O contract/instrument master (strikes/expiries)
- Legacy NSE `fo_mktlots.csv` was **discontinued Apr-2024**; the replacement contract file is **NSE Extranet (trading-member) restricted**. **No free non-broker, non-scraping F&O master exists.** Closest free path: parse the daily **F&O bhavcopy (UDiFF)** to reconstruct the live universe. Clean F&O instrument dumps otherwise come only from broker APIs (excluded).

### Also thin: India earnings *calendar* dates
- Every mainstream vendor (FMP, EODHD, Finnhub, Alpha Vantage) is US-centric here; **India earnings-date completeness is weak-to-unreliable across all** [UNVERIFIED, likely a gap]. Supplement from NSE corporate-announcements.

---

## 4. Migration note — current stack vs recommended

Your current stack: EOD OHLCV via NSE bhavcopy + yfinance (free); US via Polygon free; fundamentals via **Screener.in scraping (fragile)**; macro via FRED/RBI/MoSPI; news via RSS+FinBERT.

| Current source | Verdict | Action |
|---|---|---|
| **NSE/BSE bhavcopy (EOD)** | **Already good enough** — canonical, free. Just prefer **static file downloads over `/api` scraping** (ToS + anti-bot). | Keep. Harden the downloader (proper headers, retries, cache). |
| **yfinance (IN+US)** | **OK as a free fallback**, but unofficial Yahoo scraping — no SLA, frequent HTTP 429/IP blocks (tightened 2025), ToS gray for automated use, commercial/redistribution prohibited. | Keep as *fallback only*. For a reliable primary, move to **EODHD $19.99** (verified NSE+BSE, adjusted, symbol master). |
| **Polygon free (US)** | **Fine for US** (5 calls/min free; deep US history). Zero India value. Note **mid-rebrand to "Massive"** — re-verify URLs/pricing. | Keep for US, or fold US into EODHD/Twelve Data to consolidate vendors. |
| **Screener.in scraping (fundamentals)** | **Biggest upgrade target.** Fragile, `robots.txt` disallows key paths, no sanctioned API. | **Upgrade → EODHD Fundamentals $59.99** (clean API, NSE+BSE+US). *Live-test India quarterly depth first — it's [UNVERIFIED].* Keep Screener Excel export as free reconciliation. |
| **RSS + FinBERT (news/sentiment)** | **Good enough for $0.** Section-level, not per-company, but your FinBERT layer adds the sentiment vendors charge for. | Keep. Only add **Finnhub** (paid) if you need clean per-company IN news→ticker mapping. |
| **FRED / RBI / MoSPI (macro)** | Good, free, authoritative. | Keep (out of scope of this vendor comparison). |
| **AMFI (implied for MF)** | **Canonical & free.** | Keep. Add mfapi.in JSON wrapper for convenience. Holdings remains a gap (§3B). |
| **(Missing) India intraday / F&O real-time** | **Your biggest capability gap.** | If needed: add **TrueData** one segment (~$17–33/mo, compliant). Otherwise stay EOD and accept the limitation. |
| **(Missing) US insider/13F** | Free and easy. | Add **SEC EDGAR** ($0). |

**Net recommendation:** Consolidate onto **EODHD** as the paid backbone (EOD + intraday-delayed + fundamentals + corp actions + symbol master, IN+US), keep the **free official spine** (NSE/BSE files, AMFI, SEC EDGAR, RSS+FinBERT, FRED/RBI), and add **TrueData** only if compliant India real-time/F&O is a hard requirement. Retire Screener.in scraping as a *primary* fundamentals source.

---

## 5. Provider quick-reference (verified pricing + key facts)

| Provider | India single-stock? | Verified price ladder (2026-07) | Key limit / license note |
|---|---|---|---|
| **EODHD** ✅ *(verified at eodhd.com/pricing)* | **Yes — NSE `.NSE` + BSE `.BSE`, verified** | Free $0 (20/day) · All-World EOD **$19.99** · EOD+Intraday Extended **$29.99** · Fundamentals **$59.99** · All-In-One **$99.99** (annual ~2mo free) | Paid = 100k calls/day, 1000/min. Consumer plans = **personal use only**; redistribution needs enterprise license. |
| **yfinance** | Yes (`.NS`/`.BO`), free, fragile | FREE (Apache-2.0 code, free Yahoo data) | Undocumented limits, frequent 429; Yahoo ToS bars automated/commercial/redistribution. No SLA. |
| **Twelve Data** | NSE(XNSE)+BSE(XBOM) **EOD only** | Free $0 (800/day) · Grow **$79** · Pro $229 · Ultra $999 · Business $499+ | Credit-metered; redistribution only from Business Venture $499. No India intraday, no news endpoint. |
| **FMP** | NSE `.NS` shallow; **BSE absent** | Free (250/day) · Starter **$22** · Premium **$59** · Ultimate **$149** *[prices UNVERIFIED — page 403'd]* | US fundamentals/13F strong; personal license non-commercial; redistribution needs separate agreement. |
| **Finnhub** | Symbol+**insider** yes; **prices enterprise-gated** | Free $0 (US, 60/min) · Mkt-Data Basic **$49.99** (US) · Std $129.99 · Pro $199.99 · Fundamentals ~$50–200/mkt · All-In-One **$3,500** | 30 calls/sec global cap; personal-use-only unless enterprise. India candles need All-In-One. |
| **Alpha Vantage** | BSE `.BSE` nominal, **stale/[UNVERIFIED]**; NSE dropped ~2020 | Free $0 (25/day) · **$49.99** (75/min) · $99.99 · $149.99 · $199.99 · $249.99 | Personal/non-commercial OK; redistribution prohibited. India unreliable. |
| **Tiingo** | **No India** (US + China only) | Free $0 · Power **$30** · Commercial **$50** | US EOD to 1962; no earnings cal; no India at all. |
| **Polygon.io ("Massive")** | **No India** (US + FX/crypto) | Free $0 (5/min) · Starter **~$29** · Developer **~$79** · Advanced **~$199** | US ticks to ~2004, 1-sec bars; split- but not dividend-adjusted. Mid-rebrand — re-verify. |
| **Intrinio** | Marginal (quote-gated NSE EOD-price only); **no BSE** | Free trial · Individual **$150** · Startup $333+ · Enterprise $1,250+ | No sub-$100 real tier; US-first. India feed price [UNVERIFIED]. |
| **Marketstack** | **Not advertised / [UNVERIFIED]** | Free $0 · Basic **$9.99** · Pro **$49.99** · Business **$149.99** | Monthly quota model; intraday US/IEX only; no derivatives; US data from Tiingo. |
| **Nasdaq Data Link (Quandl)** | **Dead** (NSE/BSE frozen ~2019) | Free legacy datasets $0 · premium per-dataset [login-gated, UNVERIFIED] | Registered free key 50k/day; premium 720k/day. US Sharadar excellent; India not viable. |
| **Databento** | **No India** (roadmap only) | Usage-based $/GB [UNVERIFIED] + plans · $125 free credit | US/global microstructure (MBO/MBP-10, ns ticks). No India tick/quote. |
| **Stooq** | Indices + INR-FX only; **no NSE/BSE stocks** | FREE (CSV) | Undocumented daily cap; JS anti-bot observed 2026-07. Hobbyist-grade. |
| **TrueData** *(India, non-broker)* | **Yes — RT + F&O, no trading account** | Velocity **₹1,440–2,796/seg** (~$17–33) *[agent-reported; truedata.in/pricing 404'd at my re-fetch — verify]* + separate exchange fees | 1-sec snapshots (not tick); official Python libs; personal single-subscriber, no redistribution. |
| **Global Datafeeds (GFDL)** *(India, non-broker)* | **Yes — RT L1 + F&O Greeks, no trading account** | Custom quote; proxy ~₹3,775/seg (~$44), combo ~₹6,415 (~$75) [UNVERIFIED] | 1-sec L1; 13+yr authorized NSE vendor; WebSocket/REST/FIX; redistribution prohibited. |
| **Sensibull** *(India F&O analytics)* | Delayed (~1-min) option chain via **Google login (no broker)** | Free (delayed view); paid Lite/Pro <$30 [UNVERIFIED] | **No official API** (scrapers = ToS breach). Broker login only for realtime/trading — avoid connecting one. |
| **Trendlyne / Tickertape** *(India)* | Rich in-product (fundamentals, MF, F&O, insider) | Tickertape Pro ₹399/mo; Trendlyne ₹2,190–11,900/yr | **No sanctioned retail API** — widgets/CSV only; scraping against ToS. Not brokerage-gated to view. |
| **smallcase Gateway** | — | — | **DISQUALIFIED** — broker-linked transactional API that can place orders. |
| **AMFI** *(India MF)* | NAV for all schemes | FREE | `NAVAll.txt`; history 90-day windows; canonical. Stock-level holdings NOT provided. |
| **SEC EDGAR** *(US)* | US insider (Form 4) + 13F | FREE | 10 req/s + User-Agent required. Authoritative. |
| **India broker APIs** (Kite/Upstox/Dhan/Angel/Fyers/ICICI/5paisa) | Best RT + F&O, cheap/free | Kite ₹500/mo; Dhan data ₹499/mo; Upstox/Angel/Fyers/ICICI/5paisa **free data** | **DISQUALIFIED** — data token = order-capable trading session. *Exception:* Upstox **Analytics Token** is read-only/order-incapable (still needs an account). |

---

## 6. Verification status / flags

**Verified at source (2026-07):** EODHD full price ladder + rate limits (eodhd.com/pricing); Alpha Vantage, Twelve Data, Tiingo, Marketstack, Intrinio price ladders; Kite ₹500/mo + Dhan ₹499 data fee; Upstox Analytics Token read-only property; AMFI/NSE/BSE/SEC endpoint URLs and formats.

**[UNVERIFIED] — confirm before relying/budgeting:**
- **FMP** all prices (pricing page returned HTTP 403 to automated fetch) — corroborated via search snippets + third-party review only.
- **Finnhub** exact per-market fundamentals price and India candle/fundamentals *depth*.
- **TrueData** Velocity prices (agent-reported; `truedata.in/pricing` 301→404 at my re-fetch) and **GFDL** API pricing; **separate exchange fees** for both.
- **EODHD** India *quarterly fundamentals depth* and **EODHD/Marketaux** explicit India-news→ticker mapping — live-test with an NSE ticker.
- India **earnings-date** completeness across all vendors (likely a gap).
- NSE option-chain **exact delay**; NSE `/api/corporates-pit` path; NSE 2025 licensed-feed **tariff** (PDF blocked); BSE "free realtime feed" conditional asterisk.
- **mfdata.in** field names/ToS; Sensibull Lite/Pro prices; Trendlyne enterprise-API pricing; Screener.in/AMFI redistribution ToS clauses.
- **Alpha Vantage** BSE data freshness (community reports NSE dropped ~2020).
- FX ~₹85/USD is approximate, not a live rate.

**Licensing bottom line:** Every commercial API here prohibits **redistribution** on personal/retail tiers — fine for an internal personal analyzer, not for republishing data. **yfinance and all India website "APIs" (NSE `/api`, Trendlyne, Tickertape, Sensibull scrapers) carry real ToS/anti-bot risk** — prefer official static files (bhavcopy, AMFI, EQUITY_L.csv) and licensed vendors (EODHD, TrueData) for anything you depend on.
