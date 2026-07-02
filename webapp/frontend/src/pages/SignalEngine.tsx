import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import MarketBadge, { marketOf } from "../components/MarketBadge";
import { Loading, Error } from "./Dashboard";

type Horizon = "SHORT" | "MID" | "LONG";
const HORIZONS: { key: Horizon; label: string; sub: string }[] = [
  { key: "SHORT", label: "📅 Short", sub: "1-5 days" },
  { key: "MID", label: "📆 Mid", sub: "2-8 weeks" },
  { key: "LONG", label: "🗓️ Long", sub: "3-12 months" },
];

const SIGNAL_CLASS: Record<string, string> = {
  STRONG_BUY: "bg-green-600 text-white",
  BUY: "bg-buy/20 text-buy border border-buy/40",
  WATCH: "bg-watch/20 text-watch border border-watch/40",
  SELL: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
  STRONG_SELL: "bg-red-600 text-white",
};
const CONF_CLASS: Record<string, string> = {
  HIGH: "bg-buy/15 text-buy", MEDIUM: "bg-watch/15 text-watch", LOW: "bg-slate-600/20 text-slate-400",
};

function SignalPill({ t }: { t?: string }) {
  if (!t) return <span className="text-slate-600 text-xs">—</span>;
  return <span className={`px-2 py-0.5 rounded text-xs font-semibold whitespace-nowrap ${SIGNAL_CLASS[t] || ""}`}>{t.replace("_", " ")}</span>;
}
function pillarColor(v: number | null) {
  if (v == null) return "text-slate-500";
  return v >= 60 ? "text-buy" : v <= 41 ? "text-sell" : "text-watch";
}

export default function SignalEngine() {
  const [data, setData] = useState<any[] | null>(null);
  const [err, setErr] = useState<string>();
  const [horizon, setHorizon] = useState<Horizon>("SHORT");
  const [market, setMarket] = useState<"all" | "india" | "us">("india");
  const [agreeOnly, setAgreeOnly] = useState(false);
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    api.signalsExplained().then((d) => setData(d.stocks)).catch((e) => setErr(String(e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    let r = data;
    if (market !== "all") r = r.filter((x) => marketOf(x.exchange) === market);
    if (agreeOnly) r = r.filter((x) => x.horizons?.[horizon]?.all_pillars_agree);
    if (q) r = r.filter((x) => x.symbol.toLowerCase().includes(q.toLowerCase()) || (x.industry || "").toLowerCase().includes(q.toLowerCase()));
    return [...r].sort((a, b) => (b.horizons?.[horizon]?.overall_score ?? 0) - (a.horizons?.[horizon]?.overall_score ?? 0));
  }, [data, market, agreeOnly, horizon, q]);

  if (err) return <Error msg={err} />;
  if (!data) return <Loading />;
  if (data.length === 0)
    return <div className="card p-6 text-sm text-slate-400">No explainable signals computed yet. Run the signal engine (nse_signals) or the backfill.</div>;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">🎯 Signal Engine</h1>
        <p className="text-sm text-slate-400">4-pillar explainable signals — technical · fundamental · flows · external. Click a row for the full breakdown.</p>
      </div>

      {/* Horizon tabs */}
      <div className="flex gap-2 border-b border-edge">
        {HORIZONS.map((h) => (
          <button key={h.key} onClick={() => setHorizon(h.key)}
            className={`px-4 py-2 text-sm ${horizon === h.key ? "text-indigo-400 border-b-2 border-indigo-400" : "text-slate-400 hover:text-slate-200"}`}>
            {h.label} <span className="text-[10px] text-slate-500">{h.sub}</span>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md overflow-hidden border border-edge">
          {([["india", "🇮🇳 India"], ["us", "🇺🇸 US"], ["all", "All"]] as const).map(([m, lbl]) => (
            <button key={m} onClick={() => setMarket(m)}
              className={`px-3 py-1 text-xs ${market === m ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>{lbl}</button>
          ))}
        </div>
        <button onClick={() => setAgreeOnly((v) => !v)}
          className={`px-3 py-1 rounded-md text-xs border ${agreeOnly ? "border-buy/40 text-buy bg-buy/10" : "border-edge text-slate-400 hover:text-slate-200"}`}>
          ⭐ All pillars agree
        </button>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symbol/industry…"
          className="bg-ink border border-edge rounded-md px-3 py-1 text-xs outline-none focus:border-indigo-500" />
        <span className="text-xs text-slate-500">{rows.length} stocks</span>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr>
            <th className="th">Symbol</th><th className="th">Market</th>
            <th className="th">Short</th><th className="th">Mid</th><th className="th">Long</th>
            <th className="th text-right">Overall</th><th className="th">Conf</th><th className="th">Pillars (T·F·FL·E)</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => {
              const hz = r.horizons?.[horizon] || {};
              return (
                <tr key={r.stock_id} onClick={() => setOpenId(r.stock_id)} className="hover:bg-edge/40 cursor-pointer">
                  <td className="td">
                    <span className="font-medium text-indigo-300">{r.symbol}</span>
                    {hz.all_pillars_agree && <span title="All pillars agree" className="ml-1">⭐</span>}
                    <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{r.industry || ""}</div>
                  </td>
                  <td className="td"><MarketBadge exchange={r.exchange} /></td>
                  <td className="td"><SignalPill t={r.horizons?.SHORT?.signal_type} /></td>
                  <td className="td"><SignalPill t={r.horizons?.MID?.signal_type} /></td>
                  <td className="td"><SignalPill t={r.horizons?.LONG?.signal_type} /></td>
                  <td className="td text-right font-semibold">{hz.overall_score != null ? Number(hz.overall_score).toFixed(0) : "—"}</td>
                  <td className="td"><span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${CONF_CLASS[hz.confidence] || ""}`}>{hz.confidence || "—"}</span></td>
                  <td className="td">
                    <div className="flex gap-1.5 text-[11px] tabular-nums">
                      {[["T", r.technical_score], ["F", r.fundamental_score], ["FL", r.flow_score], ["E", r.external_score]].map(([k, v]: any) => (
                        <span key={k} className={pillarColor(v == null ? null : Number(v))}>{k}:{v == null ? "–" : Number(v).toFixed(0)}</span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {openId != null && <ExplanationPanel stockId={openId} horizon={horizon} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function PillarBlock({ title, score, reasoning }: { title: string; score: any; reasoning: any }) {
  return (
    <div className="border-t border-edge pt-2">
      <div className="text-sm font-semibold text-slate-200 mb-1">{title} <span className={pillarColor(score == null ? null : Number(score))}>({score == null ? "n/a" : `${Number(score).toFixed(0)}/100`})</span></div>
      <ul className="space-y-0.5">
        {(reasoning || []).map((line: string, i: number) => <li key={i} className="text-xs text-slate-300">{line}</li>)}
      </ul>
    </div>
  );
}

function ExplanationPanel({ stockId, horizon, onClose }: { stockId: number; horizon: Horizon; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();
  useEffect(() => {
    setD(null);
    api.signalExplanation(stockId, horizon).then(setD).catch((e) => setErr(String(e)));
  }, [stockId, horizon]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md h-full bg-ink border-l border-edge overflow-y-auto p-4" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-slate-200 text-sm">✕</button>
        {err && <Error msg={err} />}
        {!d && !err && <Loading />}
        {d && (
          <div className="space-y-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100">{d.symbol}</h2>
                <MarketBadge exchange={d.exchange} />
                {d.all_pillars_agree && <span title="All pillars agree">⭐</span>}
              </div>
              <div className="text-sm mt-1">
                <span className="text-slate-400">{horizon} · </span>
                <SignalPill t={d.signal_type} />
                <span className="ml-2 font-semibold text-slate-100">{d.overall_score != null ? `${Number(d.overall_score).toFixed(0)}/100` : ""}</span>
                <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${CONF_CLASS[d.confidence] || ""}`}>Confidence: {d.confidence}</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">{d.name} · {d.industry}</div>
            </div>

            <PillarBlock title="📊 Technical" score={d.technical_score} reasoning={d.technical_reasoning} />
            <PillarBlock title="📈 Fundamental" score={d.fundamental_score} reasoning={d.fundamental_reasoning} />
            <PillarBlock title="💰 Flows & Sentiment" score={d.flow_score} reasoning={d.flow_reasoning} />
            <PillarBlock title="🌐 External Sentiment" score={d.external_score} reasoning={d.external_reasoning} />

            {d.contrary_indicators?.length > 0 && (
              <div className="border-t border-edge pt-2">
                <div className="text-sm font-semibold text-orange-400 mb-1">⚠️ Contrary Indicators</div>
                <ul className="space-y-0.5">{d.contrary_indicators.map((c: string, i: number) => <li key={i} className="text-xs text-slate-300">• {c}</li>)}</ul>
              </div>
            )}
            {d.what_would_change?.length > 0 && (
              <div className="border-t border-edge pt-2">
                <div className="text-sm font-semibold text-indigo-300 mb-1">🔄 What would change this signal?</div>
                <ul className="space-y-0.5">{d.what_would_change.map((c: string, i: number) => <li key={i} className="text-xs text-slate-300">• {c}</li>)}</ul>
              </div>
            )}
            <div className="border-t border-edge pt-2">
              <div className="text-sm font-semibold text-slate-400 mb-1">👥 Advisor Opinions</div>
              <div className="text-xs text-slate-500">Coming soon — plug in your trusted advisors here.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
