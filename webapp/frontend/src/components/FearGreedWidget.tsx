import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceArea,
} from "recharts";
import { api, FearGreed, FearGreedMarket, fgColor } from "../api";

// Semicircular gauge (0-100) for a single market.
function Gauge({ score }: { score: number | null }) {
  const v = score ?? 0;
  const angle = -90 + (v / 100) * 180; // -90 (left) .. +90 (right)
  const color = fgColor(score);
  return (
    <svg viewBox="0 0 120 70" className="w-32 h-20">
      {/* colored arc segments */}
      {[
        ["#ef4444", -90, -54], ["#f97316", -54, -18], ["#eab308", -18, 18],
        ["#84cc16", 18, 54], ["#22c55e", 54, 90],
      ].map(([c, a0, a1], i) => {
        const p = (a: number) => {
          const r = (a * Math.PI) / 180;
          return [60 + 50 * Math.sin(r), 60 - 50 * Math.cos(r)];
        };
        const [x0, y0] = p(a0 as number), [x1, y1] = p(a1 as number);
        return <path key={i} d={`M ${x0} ${y0} A 50 50 0 0 1 ${x1} ${y1}`} stroke={c as string} strokeWidth={9} fill="none" strokeLinecap="butt" />;
      })}
      {/* needle */}
      <line x1={60} y1={60} x2={60 + 42 * Math.sin((angle * Math.PI) / 180)} y2={60 - 42 * Math.cos((angle * Math.PI) / 180)}
        stroke={color} strokeWidth={2.5} />
      <circle cx={60} cy={60} r={4} fill={color} />
      <text x={60} y={40} textAnchor="middle" className="fill-slate-100" style={{ fontSize: 16, fontWeight: 700 }}>
        {score == null ? "—" : Math.round(score)}
      </text>
    </svg>
  );
}

function Market({ title, m, onExpand }: { title: string; m: FearGreedMarket; onExpand: () => void }) {
  const last7 = m.history.slice(-7);
  const yesterday = m.history.length >= 2 ? m.history[m.history.length - 2]?.value : null;
  const change = m.score != null && yesterday != null ? m.score - yesterday : null;
  const arrow = change == null ? "" : change > 1 ? "↑" : change < -1 ? "↓" : "→";
  const arrowColor = change == null ? "" : change > 1 ? "text-buy" : change < -1 ? "text-sell" : "text-slate-400";

  // Format date as "28-Jun"
  const formatDate = (d: string | null) => {
    if (!d) return "—";
    const dt = new Date(d);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${dt.getDate()}-${months[dt.getMonth()]}`;
  };

  return (
    <button onClick={onExpand}
      className="flex-1 flex flex-col items-center rounded-lg border border-edge px-3 py-2 hover:border-indigo-500/50 transition-colors"
      title="Click for 30-day chart">
      <div className="text-xs text-slate-400">{title}</div>
      <Gauge score={m.score} />
      <div className="flex items-center gap-1">
        <span className="text-xs font-medium" style={{ color: fgColor(m.score) }}>{m.rating ?? "—"}</span>
        {arrow && <span className={`text-xs font-bold ${arrowColor}`}>{arrow}</span>}
      </div>
      {/* Yesterday's value */}
      {yesterday != null && (
        <div className="text-[10px] text-slate-500">
          Yesterday: {Math.round(yesterday)}
        </div>
      )}
      {/* Last updated date */}
      <div className="text-[10px] text-slate-500 mt-0.5">
        Updated: {formatDate(m.date)}
      </div>
      {/* 7-day sparkline trend */}
      {last7.length > 1 && (
        <div className="flex items-end gap-0.5 h-6 mt-1">
          {last7.map((p, i) => (
            <span key={i} className="w-1.5 rounded-sm" style={{ height: `${Math.max(8, p.value)}%`, background: fgColor(p.value) }}
              title={`${p.date}: ${Math.round(p.value)}`} />
          ))}
        </div>
      )}
    </button>
  );
}

export default function FearGreedWidget() {
  const [fg, setFg] = useState<FearGreed | null>(null);
  const [expanded, setExpanded] = useState<null | "india" | "us">(null);

  useEffect(() => { api.fearGreed().then(setFg).catch(() => setFg(null)); }, []);
  if (!fg) return null;

  const chartData = expanded
    ? fg[expanded].history.slice(-30).map((p) => ({ date: p.date, value: Math.round(p.value) }))
    : [];

  return (
    <div className="card p-3">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold text-slate-200">Fear &amp; Greed</h2>
        {expanded && (
          <button onClick={() => setExpanded(null)} className="text-xs text-slate-400 hover:text-slate-200">✕ close</button>
        )}
      </div>
      {!expanded ? (
        <div className="flex gap-3">
          <Market title="🇮🇳 India" m={fg.india} onExpand={() => setExpanded("india")} />
          <Market title="🇺🇸 US (CNN)" m={fg.us} onExpand={() => setExpanded("us")} />
        </div>
      ) : (
        <div>
          <div className="text-xs text-slate-400 mb-1">
            {expanded === "india" ? "🇮🇳 India" : "🇺🇸 US"} — last 30 days
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <ReferenceArea y1={0} y2={25} fill="#ef4444" fillOpacity={0.06} />
              <ReferenceArea y1={25} y2={45} fill="#f97316" fillOpacity={0.06} />
              <ReferenceArea y1={55} y2={75} fill="#84cc16" fillOpacity={0.06} />
              <ReferenceArea y1={75} y2={100} fill="#22c55e" fillOpacity={0.06} />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} tickFormatter={(d) => String(d).slice(5)} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#94a3b8" }} />
              <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", fontSize: 12 }} />
              <Line type="monotone" dataKey="value" stroke="#818cf8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
