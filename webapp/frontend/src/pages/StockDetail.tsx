import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Bar,
  ComposedChart, Cell,
} from "recharts";
import { api, fmt } from "../api";
import SignalBadge from "../components/SignalBadge";
import MarketBadge, { marketOf } from "../components/MarketBadge";
import { Loading, Error } from "./Dashboard";
import LastUpdated from "../components/LastUpdated";
import PeHistoryChart from "../components/PeHistoryChart";
import { QuarterlyResults, Financials, Concalls } from "../components/StockTabs";

const TABS = ["Overview", "Quarterly Results", "Financials", "Concalls"] as const;
type Tab = (typeof TABS)[number];

export default function StockDetail() {
  const { id } = useParams();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();
  const [tab, setTab] = useState<Tab>("Overview");

  useEffect(() => {
    setD(null);
    setTab("Overview");
    api.stock(Number(id)).then(setD).catch((e) => setErr(String(e)));
  }, [id]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const { stock, signal, prices, indicators, news, insider, shareholding, fundamentals } = d;

  const us = marketOf(stock.exchange) === "us";
  const money = (v: any) => us ? (v == null ? "—" : `$${fmt.num(v)}`) : fmt.rupee(v);

  // Merge price + indicator series by date for charts.
  const indByDate: Record<string, any> = {};
  indicators.forEach((r: any) => (indByDate[r.date] = r));
  const series = prices.map((p: any, i: number) => {
    const prevClose = i > 0 ? num(prices[i - 1].close) : null;
    const close = num(p.close);
    return {
      date: p.date.slice(5), // MM-DD
      close,
      up: prevClose == null || close == null ? true : close >= prevClose, // day direction
      volume: num(p.volume),
      volume_sma20: num(indByDate[p.date]?.volume_sma_20),
      obv: num(indByDate[p.date]?.obv),
      vwap: num(indByDate[p.date]?.vwap),
      sma50: num(indByDate[p.date]?.sma_50),
      sma200: num(indByDate[p.date]?.sma_200),
      rsi: num(indByDate[p.date]?.rsi_14),
      macd: num(indByDate[p.date]?.macd),
      macd_signal: num(indByDate[p.date]?.macd_signal),
    };
  });
  const latestSh = shareholding[0];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-100">{stock.symbol}</h1>
            {signal && <SignalBadge verdict={signal.verdict} />}
            <MarketBadge exchange={stock.exchange} />
          </div>
          <p className="text-sm text-slate-400">{stock.name}</p>
          {(stock.sector || stock.industry) && (
            <p className="text-xs text-slate-500">
              {stock.sector}{stock.sector && stock.industry ? " · " : ""}{stock.industry}
            </p>
          )}
          <div className="mt-1"><LastUpdated page="stock" /></div>
        </div>
        {signal && (
          <div className="text-right">
            <div className="text-2xl font-semibold text-slate-100">{money(signal.close)}</div>
            <div className="text-xs text-slate-400">
              RSI {fmt.num(signal.rsi_14, 1)} · MACD {fmt.num(signal.macd, 2)}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-edge">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm -mb-px border-b-2 ${tab === t ? "border-indigo-400 text-slate-100" : "border-transparent text-slate-400 hover:text-slate-200"}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Quarterly Results" && <QuarterlyResults stockId={Number(id)} />}
      {tab === "Financials" && <Financials stockId={Number(id)} />}
      {tab === "Concalls" && <Concalls stockId={Number(id)} />}

      {tab === "Overview" && <>
      {/* Price + moving averages + VWAP */}
      <Panel title="Price, moving averages & VWAP (last ~250 sessions)">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1f2c44" />
            <XAxis dataKey="date" tick={tick} minTickGap={40} />
            <YAxis tick={tick} domain={["auto", "auto"]} />
            <Tooltip contentStyle={ttStyle} />
            <Line type="monotone" dataKey="close" stroke="#818cf8" dot={false} strokeWidth={2} name="Close" />
            <Line type="monotone" dataKey="sma50" stroke="#34d399" dot={false} strokeWidth={1} name="SMA50" />
            <Line type="monotone" dataKey="sma200" stroke="#f59e0b" dot={false} strokeWidth={1} name="SMA200" />
            <Line type="monotone" dataKey="vwap" stroke="#22d3ee" dot={false} strokeWidth={1} strokeDasharray="4 3" name="VWAP(20)" />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <div className="grid lg:grid-cols-2 gap-5">
        <Panel title="RSI (14)">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid stroke="#1f2c44" />
              <XAxis dataKey="date" tick={tick} minTickGap={40} />
              <YAxis domain={[0, 100]} tick={tick} />
              <Tooltip contentStyle={ttStyle} />
              <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 4" />
              <ReferenceLine y={30} stroke="#16a34a" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="rsi" stroke="#a78bfa" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="MACD">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid stroke="#1f2c44" />
              <XAxis dataKey="date" tick={tick} minTickGap={40} />
              <YAxis tick={tick} />
              <Tooltip contentStyle={ttStyle} />
              <ReferenceLine y={0} stroke="#475569" />
              <Line type="monotone" dataKey="macd" stroke="#60a5fa" dot={false} strokeWidth={2} name="MACD" />
              <Line type="monotone" dataKey="macd_signal" stroke="#f87171" dot={false} strokeWidth={1} name="Signal" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      {/* Fundamentals */}
      {fundamentals && (
        <Panel title="Fundamentals">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
            {[
              ["P/E", fundamentals.pe_ratio], ["P/B", fundamentals.pb_ratio],
              ["ROE", fundamentals.roe], ["ROCE %", fundamentals.roce_pct],
              ["EPS", fundamentals.eps], ["D/E", fundamentals.debt_to_equity],
              ["Mkt Cap", fundamentals.market_cap], ["Promoter %", fundamentals.promoter_holding_pct],
              ["Div Yld %", fundamentals.dividend_yield_pct], ["Book Val", fundamentals.book_value],
            ].map(([k, v]) => (
              <div key={k as string}>
                <div className="stat-label">{k}</div>
                <div className="text-base font-semibold text-slate-100">{fmt.num(v as number)}</div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* P/E ratio history with valuation zones */}
      <Panel title="P/E ratio history — current vs 1yr / 5yr average">
        <PeHistoryChart stockId={Number(id)} />
      </Panel>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* Volume — bars coloured by day direction + 20d average overlay */}
        <Panel title="Volume (green = up day, red = down day) + 20d avg">
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid stroke="#1f2c44" />
              <XAxis dataKey="date" tick={tick} minTickGap={40} />
              <YAxis tick={tick} />
              <Tooltip contentStyle={ttStyle} />
              <Bar dataKey="volume" name="Volume">
                {series.map((r: any, i: number) => (
                  <Cell key={i} fill={r.up ? "#16a34a99" : "#dc262699"} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="volume_sma20" stroke="#eab308" dot={false} strokeWidth={1.5} name="Vol SMA20" />
            </ComposedChart>
          </ResponsiveContainer>
        </Panel>

        {/* OBV — On Balance Volume */}
        <Panel title="On Balance Volume (OBV)">
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid stroke="#1f2c44" />
              <XAxis dataKey="date" tick={tick} minTickGap={40} />
              <YAxis tick={tick} domain={["auto", "auto"]} tickFormatter={(v) => fmt.num(v, 0)} width={48} />
              <Tooltip contentStyle={ttStyle} />
              <Line type="monotone" dataKey="obv" stroke="#38bdf8" dot={false} strokeWidth={2} name="OBV" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* Shareholding */}
        <Panel title={`Shareholding ${latestSh ? `(${latestSh.quarter_end})` : ""}`}>
          {latestSh ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                ["Promoter", latestSh.promoter_pct], ["FII", latestSh.fii_pct],
                ["DII", latestSh.dii_pct], ["Public", latestSh.public_pct],
                ["Govt", latestSh.government_pct],
              ].map(([k, v]) => (
                <div key={k as string}>
                  <div className="stat-label">{k}</div>
                  <div className="stat-value">{fmt.pct(v as number, 1)}</div>
                </div>
              ))}
            </div>
          ) : (
            <Empty />
          )}
        </Panel>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* News */}
        <Panel title="Recent news & sentiment">
          {news.length ? (
            <ul className="space-y-2">
              {news.map((n: any, i: number) => (
                <li key={i} className="text-sm">
                  <a href={n.url || "#"} target="_blank" rel="noreferrer" className="text-slate-200 hover:text-indigo-300">
                    {n.headline}
                  </a>
                  <span className={`ml-2 text-[11px] ${sentClass(n.sentiment)}`}>{n.sentiment}</span>
                  <div className="text-[11px] text-slate-500">{n.source} · {n.date}</div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )}
        </Panel>

        {/* Insider / bulk deals */}
        <Panel title="Bulk & block deals">
          {insider.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr><th className="th">Date</th><th className="th">Client</th><th className="th">Txn</th><th className="th text-right">Qty</th><th className="th text-right">Price</th></tr></thead>
                <tbody>
                  {insider.map((b: any, i: number) => (
                    <tr key={i}>
                      <td className="td">{b.date}</td>
                      <td className="td truncate max-w-[160px]">{b.client_name}</td>
                      <td className={`td ${b.transaction === "BUY" ? "text-buy" : "text-sell"}`}>{b.transaction}</td>
                      <td className="td text-right">{fmt.num(b.quantity, 0)}</td>
                      <td className="td text-right">{fmt.rupee(b.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty />
          )}
        </Panel>
      </div>
      </>}
    </div>
  );
}

const tick = { fill: "#64748b", fontSize: 11 };
const ttStyle = { background: "#111a2e", border: "1px solid #1f2c44", borderRadius: 8, fontSize: 12 };

function num(v: any): number | null {
  return v === null || v === undefined ? null : Number(v);
}
function sentClass(s: string) {
  return s === "positive" ? "text-buy" : s === "negative" ? "text-sell" : "text-slate-400";
}
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-3">{title}</div>
      {children}
    </div>
  );
}
function Empty() {
  return <div className="text-sm text-slate-500">No data.</div>;
}
