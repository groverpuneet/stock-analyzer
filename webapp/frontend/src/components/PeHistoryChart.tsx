import { useEffect, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";

// PE ratio history with cheap (bottom 25%) / fair / expensive (top 25%) shaded
// zones derived from the stock's own 5yr range, plus current and 1yr/5yr avg lines.

export default function PeHistoryChart({ stockId }: { stockId: number }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setD(null); setErr(false);
    api.peHistory(stockId).then(setD).catch(() => setErr(true));
  }, [stockId]);

  if (err) return null;
  if (!d) return <div className="text-sm text-slate-500">Loading P/E history…</div>;
  if (!d.series?.length) return <div className="text-sm text-slate-500">No P/E history available.</div>;

  const series = d.series.map((p: any) => ({ date: String(p.date).slice(0, 7), pe: p.pe }));
  const zone = (v: number) => (v <= d.p25 ? "cheap" : v >= d.p75 ? "expensive" : "fair");
  const curZone = zone(d.current);
  const zoneColor: Record<string, string> = { cheap: "text-buy", fair: "text-watch", expensive: "text-sell" };

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Stat label="Current P/E" value={d.current} sub={<span className={zoneColor[curZone]}>{curZone} · {d.percentile}%ile</span>} />
        <Stat label="1yr avg" value={d.avg_1yr} />
        <Stat label="5yr avg" value={d.avg_5yr} />
        <Stat label="5yr range" value={`${d.min_5yr}–${d.max_5yr}`} />
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#1f2c44" />
          {/* shaded valuation zones (5yr range) */}
          <ReferenceArea y1={d.min_5yr} y2={d.p25} fill="#16a34a" fillOpacity={0.10} />
          <ReferenceArea y1={d.p25} y2={d.p75} fill="#d97706" fillOpacity={0.08} />
          <ReferenceArea y1={d.p75} y2={Math.max(d.max_5yr, d.current)} fill="#dc2626" fillOpacity={0.10} />
          <XAxis dataKey="date" tick={tick} minTickGap={50} />
          <YAxis tick={tick} domain={["auto", "auto"]} />
          <Tooltip contentStyle={ttStyle} formatter={(v: any) => [v, "P/E"]} />
          <ReferenceLine y={d.avg_5yr} stroke="#94a3b8" strokeDasharray="5 4" label={{ value: "5yr avg", fill: "#94a3b8", fontSize: 10, position: "insideTopRight" }} />
          <ReferenceLine y={d.avg_1yr} stroke="#60a5fa" strokeDasharray="3 3" />
          <Area type="monotone" dataKey="pe" stroke="#a78bfa" fill="#a78bfa22" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="text-[11px] text-slate-500 mt-2 flex gap-4">
        <span><span className="inline-block w-2 h-2 bg-buy/40 mr-1" />cheap (≤25%)</span>
        <span><span className="inline-block w-2 h-2 bg-watch/40 mr-1" />fair</span>
        <span><span className="inline-block w-2 h-2 bg-sell/40 mr-1" />expensive (≥75%)</span>
      </div>
    </div>
  );
}

const tick = { fill: "#64748b", fontSize: 11 };
const ttStyle = { background: "#111a2e", border: "1px solid #1f2c44", borderRadius: 8, fontSize: 12 };

function Stat({ label, value, sub }: { label: string; value: any; sub?: any }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? "—"}</div>
      {sub && <div className="text-[11px]">{sub}</div>}
    </div>
  );
}
