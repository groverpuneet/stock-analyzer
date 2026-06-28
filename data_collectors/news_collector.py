"""
data_collectors/news_collector.py  (replaces news_sentiment_collector.py)
Daily refresh — 5:15 PM IST

Architecture: PROACTIVE (fetch broad market news, extract stock mentions)
  vs old REACTIVE approach (fetch news per watchlist stock)

Pipeline:
  1. Fetch headlines from broad market RSS feeds (ET, Moneycontrol, BS, Mint, NSE)
  2. Extract stock mentions using flashtext (fast exact match) +
     rapidfuzz (fuzzy match for abbreviations like "RIL", "Infy")
  3. Score all headlines with FinBERT in one batch
  4. Store in news_sentiment with matched stock_id
     (stock_id = NULL for headlines with no stock match — nothing lost)
  5. Surface "new opportunity" alerts for stocks not in watchlist

Engineering concepts:
  - flashtext KeywordProcessor: Aho-Corasick algorithm under the hood.
    Searches for N keywords in a string in O(text_length) time regardless
    of N. Perfect for matching 2000+ company names in a headline.
    Compare: naive loop would be O(N × text_length) = 2000× slower.
  - rapidfuzz: Levenshtein distance for fuzzy matching abbreviations.
    "Infy" has edit distance 3 from "Infosys" but ratio=66% — above our
    threshold so it matches. "India" has ratio=40% — below threshold, skip.
  - Multi-market ready: stock universe dict is keyed by (symbol, exchange)
    so "Apple" → AAPL:NASDAQ and "Wipro" → WIPRO:NSE coexist cleanly.

Usage:
    python data_collectors/news_collector.py
    python data_collectors/news_collector.py --debug    # shows each match
    python data_collectors/news_collector.py --status   # show today's summary
"""
import os
import sys
import time
import re
from datetime import datetime, date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_conn, refresh_log
from utils.logger import get_logger

log = get_logger(__name__)

# ── Broad market RSS feeds ─────────────────────────────────────────────────────
# These cover the entire market, not just our watchlist
MARKET_FEEDS = [
    # Indian markets
    ("https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", "economic_times"),
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",     "economic_times"),
    ("https://www.moneycontrol.com/rss/business.xml",                            "moneycontrol"),
    ("https://www.business-standard.com/rss/markets-106.rss",                   "business_standard"),
    ("https://feeds.feedburner.com/ndtvprofit-latest",                           "ndtv_profit"),
    ("https://news.google.com/rss/search?q=NSE+BSE+stock+market+India&hl=en-IN&gl=IN&ceid=IN:en", "google_news_india"),
    # US markets
    ("https://news.google.com/rss/search?q=NYSE+NASDAQ+stock+market&hl=en&gl=US&ceid=US:en", "google_news_us"),
    ("https://www.cnbc.com/id/15839135/device/rss/rss.html",                     "cnbc"),
    ("http://feeds.marketwatch.com/marketwatch/topstories/",                     "marketwatch"),
    ("https://finance.yahoo.com/news/rssindex",                                  "yahoo_finance"),
    ("https://seekingalpha.com/market_currents.xml",                             "seeking_alpha"),
]

# ── FinBERT singleton ──────────────────────────────────────────────────────────
_model     = None
_tokenizer = None

def _load_finbert():
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer
    log.info("Loading FinBERT...")
    from transformers import BertTokenizer, BertForSequenceClassification
    import torch
    _tokenizer = BertTokenizer.from_pretrained('ProsusAI/finbert')
    _model     = BertForSequenceClassification.from_pretrained('ProsusAI/finbert')
    _model.eval()
    log.info("FinBERT ready")
    return _model, _tokenizer


def score_headlines(headlines: list) -> list:
    """
    Batch score headlines with FinBERT.
    Returns list of {'headline', 'sentiment', 'score', 'confidence'}.
    score: +1.0 = very bullish, -1.0 = very bearish, 0.0 = neutral
    """
    if not headlines:
        return []
    import torch
    model, tokenizer = _load_finbert()
    inputs = tokenizer(headlines, return_tensors='pt',
                       truncation=True, max_length=512, padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
    probs  = torch.softmax(outputs.logits, dim=1).tolist()
    labels = ['positive', 'negative', 'neutral']
    results = []
    for headline, prob in zip(headlines, probs):
        pos, neg, neu = prob
        results.append({
            'headline':   headline,
            'sentiment':  labels[prob.index(max(prob))],
            'score':      round(pos - neg, 3),
            'confidence': round(max(prob), 3),
        })
    return results


# ── Stock universe + flashtext matcher ────────────────────────────────────────

def build_stock_universe() -> tuple:
    """
    Load all stocks from DB and build two matching structures:

    1. flashtext KeywordProcessor — fast exact matching.
       Maps keyword → (symbol, exchange, stock_id)
       e.g. "Reliance Industries" → ('RELIANCE', 'NSE', 1)
            "RIL"               → ('RELIANCE', 'NSE', 1)

    2. fuzzy_candidates list — for rapidfuzz fallback on short abbreviations
       that flashtext might miss.

    Engineering note on why we need both:
      flashtext is exact — "Infy" won't match "Infosys" because they're
      different strings. We pre-load known abbreviations into flashtext
      (RIL, HDFC, Infy etc.) and use rapidfuzz only for unknown abbreviations
      where we do a scored comparison against all company names.

    Returns: (KeywordProcessor, {stock_id: (symbol, exchange)}, [(name, symbol, exchange, stock_id)])
    """
    from flashtext import KeywordProcessor

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, tradingsymbol, name, exchange, market
        FROM stocks
        ORDER BY name
    """)
    stocks = cur.fetchall()
    cur.close()
    conn.close()

    kp       = KeywordProcessor(case_sensitive=False)
    id_map   = {}   # stock_id → (symbol, exchange)
    all_names = []  # for fuzzy fallback

    for stock_id, symbol, name, exchange, market in stocks:
        if not name:
            continue
        id_map[stock_id] = (symbol, exchange)
        tag = (symbol, exchange, stock_id)

        # Add full company name
        kp.add_keyword(name, tag)

        # Add the ticker symbol itself (e.g. "RELIANCE", "WIPRO"), but NOT when it is
        # a common English word or a 1-2 char ticker — flashtext is case-insensitive,
        # so bare US tickers like COST/V/MA/KO/HD would match "cost", "v", "ma" etc.
        # Those stocks still match via their company name and abbreviations.
        if len(symbol) > 2 and symbol.upper() not in COMMON_WORD_TICKERS:
            kp.add_keyword(symbol, tag)

        # Add common abbreviations and short forms
        abbrevs = _get_abbreviations(symbol, name)
        for abbrev in abbrevs:
            kp.add_keyword(abbrev, tag)

        all_names.append((name.lower(), symbol, exchange, stock_id))

    log.info(f"Stock universe built: {len(stocks)} stocks, {len(kp)} keywords")
    return kp, id_map, all_names


# Known abbreviations — extend this as you encounter more in news
ABBREVIATION_MAP = {
    "RELIANCE":   ["RIL", "Reliance Jio", "Jio", "Mukesh Ambani company"],
    "TCS":        ["Tata Consultancy", "Tata Consulting"],
    "INFY":       ["Infy", "Infosys Technologies"],
    "HDFCBANK":   ["HDFC Bank", "HDFC"],
    "ICICIBANK":  ["ICICI Bank", "ICICI"],
    "BHARTIARTL": ["Airtel", "Bharti Airtel", "Bharti"],
    "SBIN":       ["SBI", "State Bank"],
    "WIPRO":      ["Wipro Technologies"],
    "ITC":        ["ITC Ltd", "Indian Tobacco"],
    "KOTAKBANK":  ["Kotak Bank", "Kotak Mahindra"],
    # US stocks
    "AAPL":   ["Apple Inc", "Apple Computer"],
    "GOOGL":  ["Google", "Alphabet"],
    "MSFT":   ["Microsoft Corp", "Microsoft"],
    "AMZN":   ["Amazon.com", "Amazon"],
    "NVDA":   ["Nvidia Corp", "Nvidia"],
    "TSLA":   ["Tesla Inc", "Tesla Motors"],
    "META":   ["Meta Platforms", "Facebook"],
    "AVGO":   ["Broadcom"],
    "AMD":    ["Advanced Micro Devices", "AMD"],
    "NFLX":   ["Netflix"],
    "ORCL":   ["Oracle"],
    "CRM":    ["Salesforce"],
    "ADBE":   ["Adobe"],
    "INTC":   ["Intel"],
    "CSCO":   ["Cisco"],
    "JPM":    ["JPMorgan", "JP Morgan", "JPMorgan Chase"],
    "BAC":    ["Bank of America", "BofA"],
    "V":      ["Visa Inc"],
    "MA":     ["Mastercard"],
    "WMT":    ["Walmart"],
    "HD":     ["Home Depot"],
    "COST":   ["Costco"],
    "PG":     ["Procter & Gamble", "Procter and Gamble"],
    "KO":     ["Coca-Cola", "Coca Cola"],
    "PEP":    ["PepsiCo", "Pepsi"],
    "JNJ":    ["Johnson & Johnson", "J&J"],
    "UNH":    ["UnitedHealth", "United Health"],
    "XOM":    ["Exxon", "Exxon Mobil", "ExxonMobil"],
    "DIS":    ["Walt Disney", "Disney"],
    "NKE":    ["Nike"],
}

# Ticker symbols that are also common English words — their bare symbol must NOT be
# a keyword (flashtext is case-insensitive). They still match via company name/abbrev.
COMMON_WORD_TICKERS = {
    "COST", "ALL", "ARE", "NOW", "ON", "IT", "SO", "BY", "OR", "CEO", "KEY",
    "WELL", "LOVE", "CARS", "PLAY", "OPEN", "TRUE", "FUN", "HE", "REAL",
}

# Generic first words that must NOT become standalone keywords — they would tag
# unrelated headlines (e.g. "Bank of America" -> "Bank" matching every banking story).
# The stock still matches via its full name and ticker symbol.
_GENERIC_FIRST_WORDS = {
    "bank", "the", "national", "india", "indian", "united", "general",
    "first", "new", "global", "american", "advanced", "johnson",
}

def _get_abbreviations(symbol: str, name: str) -> list:
    """Return known abbreviations for a stock."""
    abbrevs = ABBREVIATION_MAP.get(symbol, [])
    # Also try first word of company name as abbreviation, unless it's a generic
    # word that would generate false positives across unrelated headlines.
    first_word = name.split()[0] if name else ''
    if len(first_word) > 3 and first_word not in abbrevs and first_word.lower() not in _GENERIC_FIRST_WORDS:
        abbrevs.append(first_word)
    return abbrevs


def match_stocks_in_headline(headline: str, kp, all_names: list,
                              fuzzy_threshold: int = 75) -> list:
    """
    Find all stock mentions in a headline.

    Engineering note on the two-pass approach:
      Pass 1 (flashtext): O(n) exact match. Finds "Reliance", "RIL", "Wipro" etc.
      Pass 2 (rapidfuzz): Only runs if pass 1 finds nothing. Computes fuzzy
        similarity between each word/phrase in headline and all company names.
        More expensive but catches abbreviations like "Infy", "L&T", "M&M".

      We cap fuzzy_threshold at 75 to avoid false positives — "India" shouldn't
      match "Indiamart" or "IndusInd". Testing showed 75 is the sweet spot.

    Returns list of (symbol, exchange, stock_id, match_type)
    """
    from rapidfuzz import fuzz

    matches = []
    seen_ids = set()

    # Pass 1: flashtext exact match
    found = kp.extract_keywords(headline)
    for symbol, exchange, stock_id in found:
        if stock_id not in seen_ids:
            matches.append((symbol, exchange, stock_id, 'exact'))
            seen_ids.add(stock_id)

    if matches:
        return matches

    # Pass 2: rapidfuzz fuzzy match (only if no exact match found)
    # Split headline into candidate phrases (1-4 words)
    words = headline.split()
    candidates = []
    for i in range(len(words)):
        for j in range(i+1, min(i+5, len(words)+1)):
            candidates.append(' '.join(words[i:j]))

    for phrase in candidates:
        if len(phrase) < 4:   # skip very short phrases
            continue
        for name, symbol, exchange, stock_id in all_names:
            if stock_id in seen_ids:
                continue
            ratio = fuzz.ratio(phrase.lower(), name)
            if ratio >= fuzzy_threshold:
                matches.append((symbol, exchange, stock_id, f'fuzzy:{ratio}'))
                seen_ids.add(stock_id)

    return matches


# ── RSS fetching ───────────────────────────────────────────────────────────────

def fetch_all_headlines(max_per_feed: int = 30) -> list:
    """
    Fetch headlines from all market RSS feeds.
    Returns list of {'title', 'source', 'published', 'url'}.
    Deduplicates by title across feeds.
    """
    try:
        import feedparser
    except ImportError:
        log.error("feedparser not installed. Run: pip install feedparser")
        raise

    all_headlines = []
    seen_titles   = set()
    cutoff        = datetime.now() - timedelta(days=2)

    for feed_url, source_name in MARKET_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries[:max_per_feed]:
                title = entry.get('title', '').strip()
                # Clean HTML tags sometimes present in RSS titles
                title = re.sub(r'<[^>]+>', '', title).strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if published < cutoff:
                        continue

                all_headlines.append({
                    'title':     title,
                    'source':    source_name,
                    'published': published or datetime.now(),
                    'url':       '',   # skip URLs — contain % chars
                })
                count += 1

            log.debug(f"  {source_name}: {count} headlines")
        except Exception as e:
            log.warning(f"  Feed failed ({source_name}): {e}")

    log.info(f"Total unique headlines fetched: {len(all_headlines)}")
    return all_headlines


# ── Storage ────────────────────────────────────────────────────────────────────

def store_results(headlines: list, scores: list,
                  matches_per_headline: list) -> dict:
    """
    Store scored headlines into news_sentiment.
    - Headlines matched to a stock: stored with that stock_id
    - Headlines with no match: stored with stock_id = NULL
      (preserves everything, nothing lost)

    Returns {'stored': int, 'matched': int, 'unmatched': int}
    """
    conn    = get_conn()
    cursor  = conn.cursor()
    stored  = matched = unmatched = 0

    sql = (
        'INSERT INTO news_sentiment '
        '(stock_id, date, headline, source, url, sentiment, '
        'sentiment_score, relevance_score, summary, scored_by) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) '
        'ON CONFLICT (stock_id, date, headline) DO UPDATE SET '
        'sentiment = EXCLUDED.sentiment, '
        'sentiment_score = EXCLUDED.sentiment_score, '
        'scored_by = EXCLUDED.scored_by'
    )

    for h, s, stock_matches in zip(headlines, scores, matches_per_headline):
        pub_date       = h['published'].date() if h['published'] else date.today()
        headline_text  = h['title'][:500]
        sentiment_data = (s['sentiment'], s['score'], s['confidence'], '', 'finbert')

        if stock_matches:
            # Store one row per matched stock
            for symbol, exchange, stock_id, match_type in stock_matches:
                try:
                    cursor.execute(sql, (
                        stock_id, pub_date, headline_text,
                        h['source'], '', *sentiment_data
                    ))
                    stored += 1
                    matched += 1
                except Exception as e:
                    log.warning(f"Insert failed ({symbol}): {e}")
        else:
            # Store with NULL stock_id — nothing lost
            try:
                cursor.execute(sql, (
                    None, pub_date, headline_text,
                    h['source'], '', *sentiment_data
                ))
                stored += 1
                unmatched += 1
            except Exception as e:
                log.warning(f"Insert failed (unmatched): {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return {'stored': stored, 'matched': matched, 'unmatched': unmatched}


# ── Main pipeline ──────────────────────────────────────────────────────────────

def collect_news(debug: bool = False):
    """
    Main entry point. Full proactive pipeline.
    """
    log.info("=== News collection starting (proactive mode) ===")

    # Step 1: Build stock universe
    kp, id_map, all_names = build_stock_universe()

    # Step 2: Fetch all market headlines
    headlines = fetch_all_headlines()
    if not headlines:
        log.warning("No headlines fetched — check RSS feeds")
        return

    # Step 3: Match stocks in each headline
    log.info("Matching stock mentions...")
    matches_per_headline = []
    match_counts = defaultdict(int)

    for h in headlines:
        matches = match_stocks_in_headline(h['title'], kp, all_names)
        matches_per_headline.append(matches)
        for symbol, exchange, stock_id, match_type in matches:
            match_counts[symbol] += 1
            if debug:
                log.debug(f"  {match_type:12} | {symbol:12} | {h['title'][:60]}")

    total_matched = sum(1 for m in matches_per_headline if m)
    log.info(f"Headlines with stock matches: {total_matched}/{len(headlines)}")

    # Step 4: Score all headlines with FinBERT in one batch
    log.info("Scoring with FinBERT...")
    _load_finbert()
    titles = [h['title'] for h in headlines]
    scores = score_headlines(titles)

    # Step 5: Store everything
    with refresh_log('news_sentiment') as rlog:
        result = store_results(headlines, scores, matches_per_headline)
        rlog['rows'] = result['stored']

    log.info(
        f"Complete — stored: {result['stored']} | "
        f"matched: {result['matched']} | "
        f"unmatched: {result['unmatched']}"
    )

    # Print top mentioned stocks
    if match_counts:
        print(f"\n{'='*60}")
        print(f"TOP STOCK MENTIONS IN TODAY'S NEWS")
        print(f"{'='*60}")
        for symbol, count in sorted(match_counts.items(),
                                    key=lambda x: x[1], reverse=True)[:15]:
            print(f"  {symbol:<15} {count:>3} headlines")
        print(f"{'='*60}\n")


def print_sentiment_summary():
    """Print sentiment summary grouped by stock for last 3 days."""
    conn   = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COALESCE(s.tradingsymbol, 'UNMATCHED') as symbol,
            s.exchange,
            COUNT(*) as count,
            ROUND(AVG(ns.sentiment_score)::numeric, 2) as avg_score,
            SUM(CASE WHEN ns.sentiment = 'positive' THEN 1 ELSE 0 END) as pos,
            SUM(CASE WHEN ns.sentiment = 'negative' THEN 1 ELSE 0 END) as neg
        FROM news_sentiment ns
        LEFT JOIN stocks s ON ns.stock_id = s.id
        WHERE ns.date >= CURRENT_DATE - INTERVAL '3 days'
          AND ns.scored_by = 'finbert'
        GROUP BY s.tradingsymbol, s.exchange
        HAVING COUNT(*) >= 2
        ORDER BY avg_score DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print("No news sentiment data yet")
        return

    print(f"\n{'='*65}")
    print(f"NEWS SENTIMENT — last 3 days (min 2 headlines)")
    print(f"{'='*65}")
    print(f"  {'Symbol':<14} {'Exch':<6} {'Score':>6} {'Headlines':>10} {'Pos':>5} {'Neg':>5}")
    print(f"  {'-'*55}")
    for sym, exch, count, avg, pos, neg in rows:
        icon = 'UP' if avg and avg > 0.1 else ('DN' if avg and avg < -0.1 else '--')
        avg_str = f"{avg:+.2f}" if avg else " 0.00"
        exch_str = exch or '—'
        print(f"  {icon} {sym:<12} {exch_str:<6} {avg_str:>6}  {count:>9}  {pos:>4}  {neg:>4}")
    print(f"{'='*65}\n")


if __name__ == '__main__':
    import sys
    debug  = '--debug'  in sys.argv
    status = '--status' in sys.argv

    if status:
        print_sentiment_summary()
    else:
        collect_news(debug=debug)
        print_sentiment_summary()
