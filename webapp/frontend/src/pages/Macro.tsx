import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Line,
  ResponsiveContainer, Cell, Tooltip, XAxis, YAxis, Legend,
} from "recharts";
import { api, fmt } from "../api";
import { Loading, Error } from "./Dashboard";
import LastUpdated from "../components/LastUpdated";

const LABELS: Record<string, string> = {
  repo_rate: "Repo Rate", reverse_repo_rate: "Reverse Repo", crr: "CRR", slr: "SLR",
  sdf_rate: "SDF Rate", wacr: "WACR", usd_inr: "USD/INR",
  gdp_growth_yoy: "GDP Growth", wpi_inflation: "WPI Inflation", cpi_inflation: "CPI Inflation",
  cpi_inflation_yoy: "CPI Inflation", fed_funds_rate: "Fed Funds Rate", unemployment_rate: "Unemployment",
  forex_reserves_total: "Total Reserves", forex_reserves_fca: "Foreign Currency Assets",
  forex_reserves_gold: "Gold", forex_reserves_sdr: "SDR", forex_reserves_imf: "IMF Position",
  bank_credit_growth_yoy: "Bank Credit Growth", non_food_credit_growth_yoy: "Non-Food Credit",
  aggregate_deposits_growth_yoy: "Deposit Growth", credit_deposit_ratio: "Credit-Deposit Ratio",
};

export default function Macro() {
  const [d, setD] = useState<any>(null);
  const [trend, setTrend] = useState<any>(null);
  const [err, setErr] = useState<string>();
  useEffect(() => {
    api.macro().then(setD).catch((e) => setErr(String(e)));
    api.fiiDiiTrend(30).then(setTrend).catch(() => setTrend(null));
  }, []);
  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const fno = d.fno;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Macro Snapshot</h1>
          <p className="text-sm text-slate-400">India and US macro, kept strictly separate — all live from the database.</p>
        </div>
        <LastUpdated page="macro" />
      </div>

      {/* ───────────────────────── India ───────────────────────── */}
      <MarketHeader flag="🇮🇳" title="India Macro" tint="border-orange-500/40" />

      <Section title="RBI Policy Rates">
        <Grid items={d.rates} suffix="%" />
      </Section>

      <Section title="Growth & Inflation">
        <Grid items={d.growth} suffix="%" />
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-4">
          <div className="text-sm font-semibold text-slate-300 mb-3">
            Forex Reserves (USD bn) — {d.forex.find((x: any) => x.indicator === "forex_reserves_total")?.period}
          </div>
          <Grid items={d.forex} suffix=" bn" />
          {d.trends.forex_reserves_total?.length > 1 && (
            <ResponsiveContainer width="100%" height={150}>
              <AreaChart data={trendRows(d.trends.forex_reserves_total)} margin={{ top: 10, right: 6, bottom: 0, left: -16 }}>
                <CartesianGrid stroke="#1f2c44" />
                <XAxis dataKey="date" tick={tick} minTickGap={30} />
                <YAxis tick={tick} domain={["auto", "auto"]} />
                <Tooltip contentStyle={ttStyle} />
                <Area type="monotone" dataKey="value" stroke="#34d399" fill="#34d39933" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card p-4">
          <div className="text-sm font-semibold text-slate-300 mb-3">Bank Credit & Deposits</div>
          <Grid items={d.credit} suffix="%" />
        </div>
      </div>

      {/* FII / DII day-over-day trend */}
      {trend && trend.series?.length > 0 && <FiiDiiTrend trend={trend} />}

      {fno && (
        <Section title={`F&O Snapshot (${fno.date})`}>
          <div className="grid grid-cols-3 gap-4">
            <Stat label="India VIX" value={fmt.num(num(fno.india_vix))} />
            <Stat label="Index PCR" value={fmt.num(num(fno.index_pcr))} />
            <Stat label="Total PCR" value={fmt.num(num(fno.total_pcr))} />
          </div>
        </Section>
      )}

      <div className="grid lg:grid-cols-2 gap-5">
        <TrendCard title="GDP Growth (YoY %)" rows={d.trends.gdp_growth_yoy} color="#60a5fa" />
        <TrendCard title="WPI Inflation (YoY %)" rows={d.trends.wpi_inflation} color="#f59e0b" />
      </div>

      {/* ───────────────────────── US ───────────────────────── */}
      <MarketHeader flag="🇺🇸" title="US Macro" tint="border-blue-500/40" />

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Policy Rate & Labour">
          <Grid items={[...(d.us?.rates || []), ...(d.us?.growth || []).filter((x: any) => x.indicator === "unemployment_rate")]} suffix="%" />
        </Section>
        <Section title="Growth & Inflation">
          <Grid items={(d.us?.growth || []).filter((x: any) => x.indicator !== "unemployment_rate")} suffix="%" />
        </Section>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <TrendCard title="US GDP Growth (YoY %)" rows={d.us?.trends?.gdp_growth_yoy} color="#60a5fa" />
        <TrendCard title="US CPI Inflation (YoY %)" rows={d.us?.trends?.cpi_inflation_yoy} color="#f59e0b" />
      </div>
    </div>
  );
}

// ── FII/DII day-over-day trend chart + summary stats ──────────────────────────
function FiiDiiTrend({ trend }: { trend: any }) {
  const s = trend.summary;
  const data = trend.series.map((r: any) => ({
    date: String(r.date).slice(5),
    fii_net: r.fii_net, dii_net: r.dii_net,
    fii_ma5: r.fii_ma5, dii_ma5: r.dii_ma5, fii_ma10: r.fii_ma10, dii_ma10: r.dii_ma10,
  }));
  const streakText = (st: any, who: string) =>
    !st || st.days < 1 ? `${who}: flat` : `${who} ${st.direction} ${st.days}d`;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="text-sm font-semibold text-slate-300">
          🇮🇳 FII / DII Day-over-Day (₹ cr, last {data.length} days) — {s.latest_date}
        </div>
        <div className="flex gap-2 text-xs">
          <Streak label={streakText(s.fii_streak, "FII")} dir={s.fii_streak?.direction} />
          <Streak label={streakText(s.dii_streak, "DII")} dir={s.dii_streak?.direction} />
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <SumStat label="FII net (today)" v={s.fii_today} sub={s.fii_change != null ? `${s.fii_change >= 0 ? "+" : ""}${fmt.num(s.fii_change, 0)} vs prev` : ""} />
        <SumStat label="DII net (today)" v={s.dii_today} sub={s.dii_change != null ? `${s.dii_change >= 0 ? "+" : ""}${fmt.num(s.dii_change, 0)} vs prev` : ""} />
        <SumStat label="FII 5-day cumulative" v={s.fii_5d_cum} sub={`10d: ${fmt.num(s.fii_10d_cum, 0)}`} />
        <SumStat label="DII 5-day cumulative" v={s.dii_5d_cum} sub={`10d: ${fmt.num(s.dii_10d_cum, 0)}`} />
      </div>

      {/* FII bars + 5/10d MA */}
      <div className="text-xs text-slate-400 mb-1">FII net (green = buying, red = selling) with 5d/10d moving averages</div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="#1f2c44" />
          <XAxis dataKey="date" tick={tick} minTickGap={16} />
          <YAxis tick={tick} />
          <Tooltip contentStyle={ttStyle} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="fii_net" name="FII net" radius={[2, 2, 0, 0]}>
            {data.map((r: any, i: number) => (
              <Cell key={i} fill={r.fii_net >= 0 ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="fii_ma5" name="FII 5d MA" stroke="#eab308" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="fii_ma10" name="FII 10d MA" stroke="#818cf8" dot={false} strokeWidth={2} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* DII bars + 5/10d MA */}
      <div className="text-xs text-slate-400 mb-1 mt-3">DII net (green = buying, red = selling) with 5d/10d moving averages</div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="#1f2c44" />
          <XAxis dataKey="date" tick={tick} minTickGap={16} />
          <YAxis tick={tick} />
          <Tooltip contentStyle={ttStyle} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="dii_net" name="DII net" radius={[2, 2, 0, 0]}>
            {data.map((r: any, i: number) => (
              <Cell key={i} fill={r.dii_net >= 0 ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="dii_ma5" name="DII 5d MA" stroke="#eab308" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="dii_ma10" name="DII 10d MA" stroke="#818cf8" dot={false} strokeWidth={2} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Streak({ label, dir }: { label: string; dir?: string }) {
  const cls = dir === "buying" ? "bg-buy/15 text-buy border-buy/30"
    : dir === "selling" ? "bg-sell/15 text-sell border-sell/30"
    : "bg-slate-600/15 text-slate-400 border-slate-600/30";
  return <span className={`px-2 py-0.5 rounded border ${cls}`}>{label}</span>;
}
function SumStat({ label, v, sub }: { label: string; v: number | null; sub?: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`text-lg font-semibold ${v == null ? "text-slate-400" : v >= 0 ? "text-buy" : "text-sell"}`}>
        {v == null ? "—" : `${v >= 0 ? "+" : ""}${fmt.num(v, 0)}`}
      </div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

const tick = { fill: "#64748b", fontSize: 11 };
const ttStyle = { background: "#111a2e", border: "1px solid #1f2c44", borderRadius: 8, fontSize: 12 };
const num = (v: any) => (v == null ? null : Number(v));
const trendRows = (rows: any[]) => rows.map((r) => ({ date: String(r.date).slice(2), value: Number(r.value) }));

function MarketHeader({ flag, title, tint }: { flag: string; title: string; tint: string }) {
  return (
    <div className={`flex items-center gap-2 border-l-4 ${tint} pl-3 py-1`}>
      <span className="text-lg">{flag}</span>
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
    </div>
  );
}
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-3">{title}</div>
      {children}
    </div>
  );
}
function Grid({ items, suffix }: { items: any[]; suffix?: string }) {
  if (!items?.length) return <div className="text-sm text-slate-500">No data.</div>;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
      {items.map((m) => (
        <div key={m.indicator}>
          <div className="stat-label">{LABELS[m.indicator] || m.indicator}</div>
          <div className="stat-value">
            {fmt.num(Number(m.value))}
            <span className="text-xs text-slate-400">{suffix}</span>
          </div>
          {m.period && <div className="text-[10px] text-slate-500">{m.period}</div>}
        </div>
      ))}
    </div>
  );
}
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}
function TrendCard({ title, rows, color }: { title: string; rows: any[]; color: string }) {
  if (!rows?.length) return null;
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-3">{title}</div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={trendRows(rows)} margin={{ top: 6, right: 6, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="#1f2c44" />
          <XAxis dataKey="date" tick={tick} minTickGap={20} />
          <YAxis tick={tick} />
          <Tooltip contentStyle={ttStyle} />
          <Bar dataKey="value" fill={color} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
