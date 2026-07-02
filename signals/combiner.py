"""Combine the four pillars into a per-horizon overall signal + metadata."""

# pillar weights per horizon (advisor = 0 for now)
HORIZON_WEIGHTS = {
    "SHORT": {"technical": 0.50, "fundamental": 0.05, "flow": 0.30, "external": 0.15},
    "MID":   {"technical": 0.25, "fundamental": 0.30, "flow": 0.25, "external": 0.20},
    "LONG":  {"technical": 0.10, "fundamental": 0.60, "flow": 0.20, "external": 0.10},
}
HORIZON_LABEL = {"SHORT": "1-5 days", "MID": "2-8 weeks", "LONG": "3-12 months"}


def _signal_type(score: float) -> tuple[str, str]:
    if score >= 75:
        return "STRONG_BUY", "STRONG"
    if score >= 60:
        return "BUY", "MODERATE"
    if score > 41:
        return "WATCH", "NEUTRAL"
    if score > 26:
        return "SELL", "MODERATE"
    return "STRONG_SELL", "STRONG"


def _lean(score):
    """+1 bullish / -1 bearish / 0 neutral for a pillar score (None -> None)."""
    if score is None:
        return None
    if score > 55:
        return 1
    if score < 45:
        return -1
    return 0


def combine(horizon: str, pillars: dict) -> dict:
    """pillars: {name: finalize()-dict} for technical/fundamental/flow/external/advisor."""
    weights = HORIZON_WEIGHTS[horizon]
    num = 0.0
    den = 0.0
    for name, w in weights.items():
        sc = pillars.get(name, {}).get("score")
        if sc is not None:
            num += w * sc
            den += w
    overall = round(num / den, 1) if den else 50.0
    signal_type, strength = _signal_type(overall)

    # agreement / confidence
    leans = {n: _lean(pillars.get(n, {}).get("score")) for n in ("technical", "fundamental", "flow", "external")}
    directional = [v for v in leans.values() if v not in (None, 0)]
    bull = sum(1 for v in directional if v > 0)
    bear = sum(1 for v in directional if v < 0)
    all_agree = len(directional) >= 2 and (bull == 0 or bear == 0)
    if all_agree and len(directional) >= 3:
        confidence = "HIGH"
    elif directional and (bull == 0 or bear == 0):
        confidence = "MEDIUM"
    elif not directional:
        confidence = "LOW"
    else:
        confidence = "LOW"  # pillars conflict

    # aggregate contrary indicators
    contrary = []
    for p in pillars.values():
        for c in p.get("contrary", []):
            if c not in contrary:
                contrary.append(c)

    # overall reasoning (one line per pillar summary)
    icon = "🟢" if overall >= 60 else "🔴" if overall <= 41 else "🟡"
    overall_reasoning = [
        f"{icon} {horizon} overall {overall:.0f}/100 → {signal_type.replace('_',' ')} "
        f"({HORIZON_LABEL[horizon]}); confidence {confidence}"
        + (" — all pillars agree" if all_agree else "")
    ]
    for name in ("technical", "fundamental", "flow", "external"):
        sc = pillars.get(name, {}).get("score")
        if sc is not None:
            overall_reasoning.append(f"• {name.capitalize()} {sc:.0f} (weight {int(weights[name]*100)}%)")

    what_would_change = _what_would_change(signal_type, pillars)

    return {
        "overall_score": overall,
        "signal_type": signal_type,
        "strength": strength,
        "confidence": confidence,
        "all_pillars_agree": all_agree,
        "overall_reasoning": overall_reasoning,
        "contrary_indicators": contrary,
        "what_would_change": what_would_change,
    }


def _what_would_change(signal_type: str, pillars: dict) -> list[str]:
    bullish = signal_type in ("STRONG_BUY", "BUY")
    out = []
    tech = pillars.get("technical", {}).get("key_metrics", {})
    rsi = tech.get("rsi_14")
    if rsi is not None:
        if bullish and rsi < 50:
            out.append("RSI crossing above 70 → overbought, trim/reduce")
        elif not bullish and rsi > 50:
            out.append("RSI dropping below 30 → oversold bounce, re-evaluate")
    if bullish:
        out.append("FII net selling for >5 straight days → downgrade")
        out.append("A negative earnings surprise → immediate review")
        out.append("MACD bearish crossover → reduce conviction")
    else:
        out.append("Sustained FII buying + insider buying → upgrade")
        out.append("An earnings beat >10% → re-rate higher")
        out.append("MACD bullish crossover + volume → reduce bearishness")
    return out
