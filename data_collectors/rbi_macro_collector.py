import os, sys, re, requests, feedparser
from bs4 import BeautifulSoup
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
DBIE_URL = "https://data.rbi.org.in/DBIE/"
RBI_RSS_URL = "https://www.rbi.org.in/Scripts/Rss.aspx"
DATA_GOV_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aae38d971ead3f022c"

MOSPI_DATASETS = {
    "cpi": {"resource_id": "9ef84268-d588-465a-a308-a864a43d0070", "indicator": "cpi_inflation", "unit": "pct",   "fields": ["combined", "rural_urban_combined", "general", "cpi_combined"]},
    "iip": {"resource_id": "b9d4ea77-91c4-4c55-b76a-dc7769be8e3e", "indicator": "iip_general",   "unit": "index", "fields": ["general_index", "general", "iip_general", "index"]},
}

LABEL_MAP = {
    "policy repo rate": "repo_rate", "reverse repo rate": "reverse_repo_rate",
    "cash reserve ratio": "crr", "statutory liquidity ratio": "slr",
    "sdf rate": "sdf_rate", "standing deposit facility": "sdf_rate",
    "cpi inflation": "cpi_inflation_rbi", "wacr": "wacr", "exchange rate": "usd_inr",
}

def scrape_dbie_homepage():
    log.info("Source 1: RBI DBIE homepage...")
    try:
        resp = requests.get(DBIE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        ticker = ""
        for sel in ["#marquee", ".marquee", "#ticker", ".ticker", "[class*=ticker]", "marquee"]:
            el = soup.select_one(sel)
            if el:
                ticker = el.get_text(" ", strip=True)
                break
        if not ticker:
            m = re.search(r"Policy Repo Rate.*?(?:Exchange Rate.*?(?:USD|INR)|$)", soup.get_text(" "), re.DOTALL)
            if m:
                ticker = m.group(0)[:500]
        if ticker:
            results = _parse_ticker(ticker)
            log.info(f"  Parsed {len(results)} indicators from DBIE")
            return results
        log.warning("  DBIE ticker not found")
    except Exception as e:
        log.warning(f"  DBIE scrape failed: {e}")
    return {}

def _parse_ticker(text):
    results = {}
    pat = re.compile(
        r"(Policy Repo Rate|Reverse Repo Rate|Cash Reserve Ratio|Statutory Liquidity Ratio"
        r"|SDF Rate|Standing Deposit Facility[^:]*Rate|CPI Inflation|WACR|Exchange Rate)"
        r"\s*:\s*([\d.]+)\s*(%)?(?:\s*\(([^)]+)\))?", re.IGNORECASE)
    for m in pat.finditer(text):
        label = m.group(1).strip().lower()
        db_key = next((v for k, v in LABEL_MAP.items() if k in label), None)
        if db_key:
            try:
                val = float(m.group(2))
                unit = "INR_per_USD" if db_key == "usd_inr" else ("pct" if m.group(3) else "index")
                results[db_key] = (val, unit, m.group(4) or date.today().strftime("%b-%y"))
            except ValueError:
                pass
    return results

def fetch_rbi_policy_releases():
    log.info("Source 2: RBI press releases RSS...")
    releases = []
    try:
        feed = feedparser.parse(RBI_RSS_URL)
        kw = ["monetary policy", "repo rate", "policy rate", "mpc", "policy statement"]
        for entry in feed.entries[:50]:
            title = entry.get("title", "")
            if any(k in title.lower() for k in kw):
                pub = datetime(*entry.published_parsed[:6]).date() if hasattr(entry, "published_parsed") and entry.published_parsed else date.today()
                releases.append({"title": title, "date": pub, "url": entry.get("link", "")})
        log.info(f"  Found {len(releases)} MPC releases")
        for r in releases[:3]:
            log.info(f"  [{r['date']}] {r['title'][:70]}")
    except Exception as e:
        log.warning(f"  RBI RSS failed: {e}")
    return releases

def fetch_mospi_data():
    log.info("Source 3: MoSPI via data.gov.in...")
    results = {}
    for name, cfg in MOSPI_DATASETS.items():
        try:
            resp = requests.get(
                f"https://api.data.gov.in/resource/{cfg['resource_id']}",
                params={"api-key": DATA_GOV_KEY, "format": "json", "limit": 5}, timeout=15)
            resp.raise_for_status()
            records = resp.json().get("records", [])
            if not records:
                log.warning(f"  {name.upper()}: no records")
                continue
            latest = records[-1]
            period = latest.get("month_year") or latest.get("period") or latest.get("year") or ""
            value = None
            for field in cfg["fields"]:
                for key in latest:
                    if field.lower() in key.lower():
                        try:
                            value = float(str(latest[key]).replace(",", ""))
                            break
                        except (ValueError, TypeError):
                            pass
                if value is not None:
                    break
            if value is not None:
                results[cfg["indicator"]] = (value, cfg["unit"], str(period))
                log.info(f"  {name.upper()}: {cfg['indicator']} = {value} ({period})")
            else:
                log.warning(f"  {name.upper()}: could not extract value. Fields: {list(latest.keys())[:6]}")
        except requests.HTTPError as e:
            log.warning(f"  {name.upper()}: HTTP {e.response.status_code}")
        except Exception as e:
            log.warning(f"  {name.upper()}: {e}")
    return results

def store_macro_indicators(indicators):
    if not indicators:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    stored = 0
    today = date.today()
    for indicator, (value, unit, period) in indicators.items():
        try:
            cur.execute("""
                INSERT INTO macro_indicators (date, market, indicator, value, unit, period, source)
                VALUES (%s, 'IN', %s, %s, %s, %s, 'rbi_dbie')
                ON CONFLICT (date, market, indicator) DO UPDATE SET value=EXCLUDED.value, period=EXCLUDED.period
            """, (today, indicator, value, unit, period))
            stored += 1
        except Exception as e:
            log.warning(f"  Insert failed {indicator}: {e}")
    conn.commit()
    cur.close()
    conn.close()
    return stored

def collect_rbi_macro(debug=False):
    log.info("=== RBI/MoSPI Macro collection starting ===")
    with refresh_log("rbi_macro") as rlog:
        indicators = {}
        indicators.update(scrape_dbie_homepage())
        fetch_rbi_policy_releases()
        indicators.update(fetch_mospi_data())
        total = store_macro_indicators(indicators)
        log.info(f"Stored {total} macro indicators")
        rlog["rows"] = total
    _print_snapshot()

def _print_snapshot():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT indicator, value, unit, period FROM macro_indicators WHERE market='IN' ORDER BY date DESC, indicator LIMIT 20")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        print("No macro data yet")
        return
    print(f"\n{'='*65}\nINDIA MACRO SNAPSHOT\n{'='*65}")
    print(f"  {'Indicator':<26} {'Value':>8}  {'Unit':<15} Period")
    print(f"  {'-'*58}")
    for ind, val, unit, period in rows:
        print(f"  {ind:<26} {float(val):>8.2f}  {unit:<15} {period}")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    import logging
    if "--debug" in sys.argv:
        log.setLevel(logging.DEBUG)
    collect_rbi_macro()
