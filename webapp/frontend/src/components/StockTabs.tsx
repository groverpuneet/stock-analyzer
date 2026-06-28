import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, fmt } from "../api";

const tick = { fill: "#64748b", fontSize: 11 };
const ttStyle = { background: "#111a2e", border: "1px solid #1f2c44", borderRadius: 8, fontSize: 12 };

function Empty({ msg = "No data yet." }: { msg?: string }) {
  return <div className="text-sm text-slate-500 py-6 text-center">{msg}</div>;
}
function pct(v: number | null | undefined) {
  if (v == null) return <span className="text-slate-600">—</span>;
  return <span className={v > 0 ? "text-buy" : v < 0 ? "text-sell" : "text-slate-400"}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}
const qlabel = (q: string) => q;

// ---------- Quarterly Results (revenue / PAT / EPS + QoQ/YoY) ----------
export function QuarterlyResults({ stockId }: { stockId: number }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.quarterlyResults(stockId).then(setD).catch(() => setD({ quarters: [] })); }, [stockId]);
  if (!d) return <Empty msg="Loading…" />;
  const rows = d.quarters as any[];
  if (!rows.length) return <Empty />;
  const chart = rows.map((r) => ({ q: qlabel(r.quarter), revenue: r.revenue, pat: r.pat, eps: r.eps }));
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="text-sm font-semibold text-slate-300 mb-3">Revenue &amp; PAT (₹ Cr) — last {rows.length} quarters</div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={chart} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1f2c44" />
            <XAxis dataKey="q" tick={tick} minTickGap={10} />
            <YAxis tick={tick} />
            <Tooltip contentStyle={ttStyle} />
            <Bar dataKey="revenue" fill="#3b4d70" name="Revenue" />
            <Line type="monotone" dataKey="pat" stroke="#34d399" strokeWidth={2} dot={false} name="PAT" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="th">Quarter</th>
              <th className="th text-right">Revenue</th>
              <th className="th text-right">QoQ</th>
              <th className="th text-right">YoY</th>
              <th className="th text-right">PAT</th>
              <th className="th text-right">QoQ</th>
              <th className="th text-right">YoY</th>
              <th className="th text-right">EPS</th>
              <th className="th text-right">YoY</th>
            </tr>
          </thead>
          <tbody>
            {[...rows].reverse().map((r) => (
              <tr key={r.period_end} className="hover:bg-edge/30">
                <td className="td font-medium text-slate-200">{r.quarter}</td>
                <td className="td text-right tabular-nums">{fmt.num(r.revenue, 0)}</td>
                <td className="td text-right tabular-nums">{pct(r.revenue_qoq)}</td>
                <td className="td text-right tabular-nums">{pct(r.revenue_yoy)}</td>
                <td className="td text-right tabular-nums">{fmt.num(r.pat, 0)}</td>
                <td className="td text-right tabular-nums">{pct(r.pat_qoq)}</td>
                <td className="td text-right tabular-nums">{pct(r.pat_yoy)}</td>
                <td className="td text-right tabular-nums">{fmt.num(r.eps, 2)}</td>
                <td className="td text-right tabular-nums">{pct(r.eps_yoy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- Financials (P&L / balance sheet / cash flow) ----------
export function Financials({ stockId }: { stockId: number }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.financials(stockId).then(setD).catch(() => setD({ financials: [] })); }, [stockId]);
  if (!d) return <Empty msg="Loading…" />;
  const rows = (d.financials as any[]).map((r) => ({ ...r, q: qlabel(r.quarter) }));
  if (!rows.length) return <Empty />;
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <ChartCard title="Revenue & EBITDA (₹ Cr)" data={rows} bars={[["revenue", "#3b4d70", "Revenue"], ["ebitda", "#6366f1", "EBITDA"]]} />
      <ChartCard title="Net Profit (₹ Cr)" data={rows} bars={[["pat", "#34d399", "PAT"]]} />
      <ChartCard title="Debt vs Cash (₹ Cr)" data={rows} bars={[["debt", "#f87171", "Debt"], ["cash", "#34d399", "Cash"]]} />
      <ChartCard title="Operating Cash Flow & Capex (₹ Cr)" data={rows} bars={[["ocf", "#60a5fa", "OCF"], ["capex", "#fbbf24", "Capex"]]} />
    </div>
  );
}

function ChartCard({ title, data, bars }: { title: string; data: any[]; bars: [string, string, string][] }) {
  const has = bars.some(([k]) => data.some((r) => r[k] != null));
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-3">{title}</div>
      {has ? (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1f2c44" />
            <XAxis dataKey="q" tick={tick} minTickGap={10} />
            <YAxis tick={tick} />
            <Tooltip contentStyle={ttStyle} />
            {bars.map(([k, c, name]) => <Bar key={k} dataKey={k} fill={c} name={name} />)}
          </BarChart>
        </ResponsiveContainer>
      ) : <Empty msg="Not available on Screener for this stock." />}
    </div>
  );
}

// ---------- Concalls (earnings call transcripts) ----------
export function Concalls({ stockId }: { stockId: number }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.concalls(stockId).then(setD).catch(() => setD({ concalls: [] })); }, [stockId]);
  if (!d) return <Empty msg="Loading…" />;
  const rows = d.concalls as any[];
  if (!rows.length) return <Empty msg="No concall transcripts found." />;
  return (
    <div className="space-y-3">
      {rows.map((c, i) => (
        <div key={i} className="card p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="font-semibold text-slate-200">{c.quarter || "Latest"} earnings call</div>
            {c.sentiment_score != null && (
              <span className={`text-xs px-2 py-0.5 rounded border ${c.sentiment_score > 0.1 ? "text-buy border-buy/30" : c.sentiment_score < -0.1 ? "text-sell border-sell/30" : "text-slate-400 border-edge"}`}>
                sentiment {Number(c.sentiment_score).toFixed(2)}
              </span>
            )}
          </div>
          {c.summary
            ? <p className="text-sm text-slate-300 mt-2 whitespace-pre-line">{c.summary}</p>
            : <p className="text-sm text-slate-500 mt-2 italic">Summary not generated yet (on-demand via FinBERT + Claude).</p>}
          {Array.isArray(c.key_themes) && c.key_themes.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {c.key_themes.map((t: string, j: number) => (
                <span key={j} className="text-[11px] bg-edge/60 rounded px-1.5 py-0.5 text-slate-300">{t}</span>
              ))}
            </div>
          )}
          {c.transcript_url && (
            <a href={c.transcript_url} target="_blank" rel="noreferrer"
              className="inline-block mt-2 text-xs text-indigo-300 hover:text-indigo-200">📄 View transcript →</a>
          )}
        </div>
      ))}
    </div>
  );
}
