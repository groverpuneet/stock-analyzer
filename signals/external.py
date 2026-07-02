"""Pillar 4 — External sentiment (fresh web + Google-News headlines, VADER-scored).

The expensive fetch (web search + RSS) is separated from scoring so the engine can
cache the raw payload in signal_explanations.cached_external_sentiment for 6 hours.
"""
import re

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .util import PillarResult

_analyzer = SentimentIntensityAnalyzer()

# headline keywords that carry extra signal
_POS = re.compile(r"\b(upgrade|beat|beats|surge|record|order win|bags order|wins|strong|outperform|buy rating|raises|hike)\b", re.I)
_NEG = re.compile(r"\b(downgrade|miss|misses|slump|plunge|probe|fraud|penalty|resign|cut|weak|sell rating|lawsuit|default)\b", re.I)


def _vader(texts: list[str]) -> float | None:
    scores = [_analyzer.polarity_scores(t)["compound"] for t in texts if t]
    return sum(scores) / len(scores) if scores else None


def _ddg_news(company: str, max_results: int = 10) -> list[str]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            res = ddgs.news(f"{company} stock", region="in-en", timelimit="w", max_results=max_results)
        return [f"{r.get('title','')} {r.get('body','')}".strip() for r in (res or [])]
    except Exception:
        return []


def _google_news(company: str, max_results: int = 10) -> list[str]:
    try:
        import feedparser
        from urllib.parse import quote
        url = f"https://news.google.com/rss/search?q={quote(company + ' NSE stock')}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        return [e.title for e in feed.entries[:max_results]]
    except Exception:
        return []


def fetch_external_sentiment(company_name: str, symbol: str) -> dict:
    """Do the network work (DDG + Google News) and return a raw, cacheable payload."""
    company = company_name or symbol
    ddg = _ddg_news(company)
    gnews = _google_news(company)
    ddg_s = _vader(ddg)
    gn_s = _vader(gnews)
    all_titles = (ddg + gnews)[:20]
    pos = sum(1 for t in all_titles if _POS.search(t))
    neg = sum(1 for t in all_titles if _NEG.search(t))
    parts = [s for s in (ddg_s, gn_s) if s is not None]
    combined = sum(parts) / len(parts) if parts else None
    return {
        "ddg_count": len(ddg), "gnews_count": len(gnews),
        "ddg_score": round(ddg_s, 3) if ddg_s is not None else None,
        "gnews_score": round(gn_s, 3) if gn_s is not None else None,
        "combined_compound": round(combined, 3) if combined is not None else None,
        "pos_keyword_hits": pos, "neg_keyword_hits": neg,
        "sample_headlines": all_titles[:5],
    }


def score_external(raw: dict | None) -> dict:
    """Build the pillar result from a (possibly cached) raw payload."""
    r = PillarResult()
    if not raw:
        r.note("No external sentiment fetched yet")
        return r.finalize()

    total = (raw.get("ddg_count", 0) or 0) + (raw.get("gnews_count", 0) or 0)
    if total == 0:
        r.note("No external news found in the last week")
        return r.finalize()

    r.metric("external_headlines", total)
    comp = raw.get("combined_compound")
    if comp is not None:
        r.metric("vader_compound", comp)
        pts = comp * 40  # compound [-1,1] -> up to ±40 around the 50 base
        if comp > 0.15:
            r.add(pts, f"Net-positive news tone across {total} recent headlines (VADER {comp:+.2f})")
        elif comp < -0.15:
            r.add(pts, f"Net-negative news tone across {total} recent headlines (VADER {comp:+.2f})")
            r.contra("Negative external news tone")
        else:
            r.note(f"Neutral external news tone across {total} headlines")

    pos, neg = raw.get("pos_keyword_hits", 0), raw.get("neg_keyword_hits", 0)
    if pos:
        r.add(min(pos * 3, 9), f"{pos} positive catalyst mention(s) (upgrade/beat/order win)")
    if neg:
        r.add(-min(neg * 3, 9), f"{neg} negative catalyst mention(s) (downgrade/miss/probe)")
        if neg >= 2:
            r.contra("Multiple negative catalysts in the news")
    if not pos and not neg and comp is not None and abs(comp) < 0.15:
        r.note("No unusual positive or negative catalysts detected")

    return r.finalize()
