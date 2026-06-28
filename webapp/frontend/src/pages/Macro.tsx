import { useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmt } from "../api";
import { Loading, Error } from "./Dashboard";
import LastUpdated from "../components/LastUpdated";

const LABELS: Record<string, string> = {
  repo_rate: "Repo Rate", reverse_repo_rate: "Reverse Repo", crr: "CRR", slr: "SLR",
  sdf_rate: "SDF Rate", wacr: "WACR", usd_inr: "USD/INR",
  gdp_growth_yoy: "GDP Growth", wpi_inflation: "WPI Inflation", cpi_inflation: "CPI Inflation",
  forex_reserves_total: "Total Reserves", forex_reserves_fca: "Foreign Currency Assets",
  forex_reserves_gold: "Gold", forex_reserves_sdr: "SDR", forex_reserves_imf: "IMF Position",
  bank_credit_growth_yoy: "Bank Credit Growth", non_food_credit_growth_yoy: "Non-Food Credit",
  aggregate_deposits_growth_yoy: "Deposit Growth", credit_deposit_ratio: "Credit-Deposit Ratio",
};

export default function Macro() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();
  useEffect(() => {
    api.macro().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const fii = d.fii_dii;
  const fno = d.fno;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Macro Snapshot</h1>
          <p className="text-sm text-slate-400">RBI rates, forex reserves, FII/DII flows, GDP & inflation — all live from the database.</p>
        </div>
        <LastUpdated page="macro" />
      </div>

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
              <AreaChart data={trend(d.trends.forex_reserves_total)} margin={{ top: 10, right: 6, bottom: 0, left: -16 }}>
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

      <div className="grid lg:grid-cols-2 gap-5">
        {fii && (
          <Section title={`FII / DII Flows (₹ cr, ${fii.date})`}>
            <div className="grid grid-cols-2 gap-4">
              <Flow label="FII Net" v={Number(fii.fii_net)} />
              <Flow label="DII Net" v={Number(fii.dii_net)} />
            </div>
          </Section>
        )}
        {fno && (
          <Section title={`F&O Snapshot (${fno.date})`}>
            <div className="grid grid-cols-3 gap-4">
              <Stat label="India VIX" value={fmt.num(num(fno.india_vix))} />
              <Stat label="Index PCR" value={fmt.num(num(fno.index_pcr))} />
              <Stat label="Total PCR" value={fmt.num(num(fno.total_pcr))} />
            </div>
          </Section>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <TrendCard title="GDP Growth (YoY %)" rows={d.trends.gdp_growth_yoy} color="#60a5fa" />
        <TrendCard title="WPI Inflation (YoY %)" rows={d.trends.wpi_inflation} color="#f59e0b" />
      </div>
    </div>
  );
}

const tick = { fill: "#64748b", fontSize: 11 };
const ttStyle = { background: "#111a2e", border: "1px solid #1f2c44", borderRadius: 8, fontSize: 12 };
const num = (v: any) => (v == null ? null : Number(v));
const trend = (rows: any[]) => rows.map((r) => ({ date: String(r.date).slice(2), value: Number(r.value) }));

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
function Flow({ label, v }: { label: string; v: number }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`text-xl font-semibold ${v >= 0 ? "text-buy" : "text-sell"}`}>
        {v >= 0 ? "+" : ""}
        {fmt.num(v, 0)}
      </div>
    </div>
  );
}
function TrendCard({ title, rows, color }: { title: string; rows: any[]; color: string }) {
  if (!rows?.length) return null;
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-3">{title}</div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={trend(rows)} margin={{ top: 6, right: 6, bottom: 0, left: -16 }}>
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
