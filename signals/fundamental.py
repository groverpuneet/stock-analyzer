"""Pillar 2 — Fundamental signals (valuation, quality, growth, earnings, analyst, ownership)."""
from datetime import date

from .util import dict_cur, f, PillarResult


def score_fundamental(conn, stock_id: int, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    r = PillarResult()
    with dict_cur(conn) as cur:
        # Latest full fundamentals row (exclude the PE-history-only series)
        cur.execute(
            """SELECT pe_ratio, pb_ratio, roe, roce_pct, debt_to_equity, opm_pct,
                      ev_ebitda, promoter_holding_pct, pledged_pct
               FROM fundamentals WHERE stock_id=%s AND source <> 'screener_pe_history'
               AND date <= %s ORDER BY date DESC LIMIT 1""", (stock_id, as_of))
        fund = cur.fetchone()

        cur.execute("SELECT pe_percentile FROM stock_scores WHERE stock_id=%s AND date <= %s "
                    "ORDER BY date DESC LIMIT 1", (stock_id, as_of))
        sc = cur.fetchone()
        pe_pct = f(sc["pe_percentile"]) if sc else None

        cur.execute(
            """SELECT quarter, period_end, revenue, pat FROM quarterly_financials
               WHERE stock_id=%s AND period_end <= %s ORDER BY period_end DESC LIMIT 6""",
            (stock_id, as_of))
        q = [dict(x) for x in cur.fetchall()]

        cur.execute(
            "SELECT surprise_pct, results_date FROM earnings_calendar WHERE stock_id=%s "
            "AND surprise_pct IS NOT NULL AND results_date <= %s ORDER BY results_date DESC LIMIT 1",
            (stock_id, as_of))
        earn = cur.fetchone()

        # NOTE: analyst consensus + FII%/DII% ownership trends now live in the FLOWS pillar
        # (stock-specific section) to avoid double-counting; fundamental keeps promoter/pledging.
        cur.execute(
            "SELECT promoter_pct FROM shareholding_pattern "
            "WHERE stock_id=%s AND quarter_end <= %s ORDER BY quarter_end DESC LIMIT 2",
            (stock_id, as_of))
        sh = [dict(x) for x in cur.fetchall()]

        cur.execute(
            "SELECT current_pledge_pct, change_pct FROM pledging_alerts WHERE stock_id=%s "
            "AND date <= %s ORDER BY date DESC LIMIT 1", (stock_id, as_of))
        pl = cur.fetchone()

    # ── Valuation ──
    if pe_pct is not None:
        r.metric("pe_percentile", round(pe_pct, 0))
        if pe_pct < 20:
            r.add(15, f"P/E at {pe_pct:.0f}th percentile of 5yr range — historically cheap")
        elif pe_pct > 80:
            r.add(-15, f"P/E at {pe_pct:.0f}th percentile of 5yr range — historically expensive")
            r.contra("Valuation rich vs own history")
        else:
            r.note(f"P/E at {pe_pct:.0f}th percentile — fairly valued")
    if fund and f(fund["ev_ebitda"]) is not None:
        r.metric("ev_ebitda", round(f(fund["ev_ebitda"]), 1))

    # ── Quality ──
    if fund:
        roe = f(fund["roe"])
        if roe is not None:
            r.metric("roe", round(roe, 1))
            if roe >= 15:
                r.add(10, f"ROE {roe:.1f}% — high-quality business")
            elif roe < 8:
                r.add(-6, f"ROE {roe:.1f}% — subpar returns on equity")
        de = f(fund["debt_to_equity"])
        if de is not None:
            r.metric("debt_to_equity", round(de, 2))
            if de < 0.5:
                r.add(6, f"Debt/equity {de:.2f} — strong balance sheet")
            elif de <= 1:
                r.add(2, f"Debt/equity {de:.2f} — manageable", icon="⚠️")
            else:
                r.add(-8, f"Debt/equity {de:.2f} — leveraged")
                r.contra("High leverage")
        opm = f(fund["opm_pct"])
        if opm is not None:
            r.metric("opm_pct", round(opm, 1))

    # ── Growth (YoY from quarterly) ──
    def yoy(field):
        if len(q) >= 5 and f(q[0][field]) is not None and f(q[4][field]) not in (None, 0):
            return (f(q[0][field]) / f(q[4][field]) - 1) * 100
        return None
    rev_g, pat_g = yoy("revenue"), yoy("pat")
    if rev_g is not None:
        r.metric("revenue_yoy", round(rev_g, 1))
        if rev_g > 15:
            r.add(8, f"Revenue +{rev_g:.0f}% YoY — strong top-line growth")
        elif rev_g < 0:
            r.add(-6, f"Revenue {rev_g:.0f}% YoY — declining sales")
            r.contra("Revenue contracting YoY")
    if pat_g is not None:
        r.metric("pat_yoy", round(pat_g, 1))
        if pat_g > 15:
            r.add(8, f"PAT +{pat_g:.0f}% YoY — profit growth")
        elif pat_g < 0:
            r.add(-6, f"PAT {pat_g:.0f}% YoY — earnings falling")
    # QoQ deceleration flag
    if len(q) >= 2 and f(q[0]["revenue"]) is not None and f(q[1]["revenue"]) not in (None, 0):
        qoq = (f(q[0]["revenue"]) / f(q[1]["revenue"]) - 1) * 100
        if qoq < -5:
            r.add(-3, f"Revenue {qoq:.0f}% QoQ — sequential slowdown", icon="⚠️")

    # ── Earnings surprise ──
    if earn and f(earn["surprise_pct"]) is not None:
        s = f(earn["surprise_pct"])
        r.metric("last_earnings_surprise_pct", round(s, 1))
        if s > 10:
            r.add(8, f"Last result beat estimates by {s:.0f}%")
        elif s < -10:
            r.add(-8, f"Last result missed estimates by {abs(s):.0f}%")

    # ── Promoter ownership trend (analyst + FII% moved to flows pillar) ──
    if len(sh) >= 2:
        pr0, pr1 = f(sh[0]["promoter_pct"]), f(sh[1]["promoter_pct"])
        if pr0 is not None and pr1 is not None and pr0 - pr1 < -0.5:
            r.add(-4, f"Promoter holding falling ({pr1:.1f}%→{pr0:.1f}%)", icon="⚠️")
            r.contra("Promoter stake declining")

    # ── Pledging ──
    if pl and f(pl["current_pledge_pct"]) is not None:
        pp = f(pl["current_pledge_pct"])
        chg = f(pl["change_pct"]) or 0
        r.metric("pledge_pct", round(pp, 1))
        if pp > 5 and chg > 5:
            r.add(-8, f"Promoter pledge rising to {pp:.0f}% — red flag")
            r.contra("Rising promoter pledging")
        elif pp > 20:
            r.add(-5, f"Promoter pledge elevated at {pp:.0f}%", icon="⚠️")

    return r.finalize()
