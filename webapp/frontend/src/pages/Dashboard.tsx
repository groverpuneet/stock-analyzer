import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt, Verdict } from "../api";
import SignalBadge from "../components/SignalBadge";
import LastUpdated from "../components/LastUpdated";

type Row = Record<string, any>;
type Dir = "asc" | "desc";

// Column definitions for the expanded dashboard table.
interface Col {
  key: string;
  label: string;
  render?: (r: Row) => any;
  num?: boolean;            // numeric sort + right align
  cls?: (v: any, r: Row) => string;
}

const cols: Col[] = [
  { key: "symbol", label: "Symbol", render: (r) => (
      <Link to={`/stock/${r.stock_id}`} className="font-medium text-indigo-300 hover:text-indigo-200">{r.symbol}</Link>
    ) },
  { key: "verdict", label: "Signal", render: (r) => <SignalBadge verdict={r.verdict as Verdict} /> },
  { key: "close", label: "Price", num: true, render: (r) => fmt.rupee(r.close) },
  { key: "day_change_pct", label: "Day %", num: true, render: (r) => fmt.pct(r.day_change_pct, 2),
    cls: (v) => (v > 0 ? "text-buy" : v < 0 ? "text-sell" : "") },
  { key: "week52_high", label: "52w H", num: true, render: (r) => fmt.num(r.week52_high) },
  { key: "week52_low", label: "52w L", num: true, render: (r) => fmt.num(r.week52_low) },
  { key: "rsi_14", label: "RSI", num: true, render: (r) => fmt.num(r.rsi_14, 1),
    cls: (v) => (v != null && v < 30 ? "text-buy" : v != null && v > 70 ? "text-sell" : "") },
  { key: "macd", label: "MACD", num: true, render: (r) => fmt.num(r.macd, 2) },
  { key: "bb_position", label: "BB %", num: true, render: (r) => fmt.num(r.bb_position, 0) },
  { key: "sma_50", label: "SMA50", num: true, render: (r) => fmt.num(r.sma_50, 0) },
  { key: "sma_200", label: "SMA200", num: true, render: (r) => fmt.num(r.sma_200, 0) },
  { key: "pe_ratio", label: "P/E", num: true, render: (r) => fmt.num(r.pe_ratio, 1) },
  { key: "pe_percentile", label: "P/E %ile", num: true, render: (r) => r.pe_percentile == null ? "—" : `${r.pe_percentile.toFixed(0)}`,
    cls: (v) => (v == null ? "" : v <= 25 ? "text-buy" : v >= 75 ? "text-sell" : "text-watch") },
  { key: "pb_ratio", label: "P/B", num: true, render: (r) => fmt.num(r.pb_ratio, 1) },
  { key: "roe", label: "ROE", num: true, render: (r) => fmt.num(r.roe, 1) },
  { key: "debt_to_equity", label: "D/E", num: true, render: (r) => fmt.num(r.debt_to_equity, 2) },
  { key: "market_cap", label: "Mkt Cap", num: true, render: (r) => fmt.num(r.market_cap, 0) },
  { key: "sentiment_score", label: "News", num: true, render: (r) =>
      r.sentiment ? <span className={sentCls(r.sentiment)}>{r.sentiment[0].toUpperCase()}{r.sentiment_score != null ? ` ${r.sentiment_score.toFixed(2)}` : ""}</span> : "—" },
  { key: "composite_score", label: "Score", num: true, render: (r) => fmt.num(r.composite_score, 1),
    cls: (v) => (v != null && v >= 60 ? "text-buy" : "") },
  { key: "rsi_rank", label: "RSI rk", num: true, render: (r) => fmt.num(r.rsi_rank, 0) },
  { key: "momentum_score", label: "Mom rk", num: true, render: (r) => fmt.num(r.momentum_score, 0) },
  { key: "macd_rank", label: "MACD rk", num: true, render: (r) => fmt.num(r.macd_rank, 0) },
  { key: "insider_net", label: "Insider", num: true, render: (r) =>
      r.insider_buys || r.insider_sells
        ? <span className={r.insider_net > 0 ? "text-buy" : r.insider_net < 0 ? "text-sell" : ""}>{r.insider_buys}B/{r.insider_sells}S</span>
        : "—" },
];

const FILTERS: (Verdict | "ALL")[] = ["ALL", "BUY", "SELL", "WATCH", "NEUTRAL"];

export default function Dashboard() {
  const [data, setData] = useState<{ stocks: Row[]; fii_dii: any } | null>(null);
  const [err, setErr] = useState<string>();
  const [sortKey, setSortKey] = useState("composite_score");
  const [dir, setDir] = useState<Dir>("desc");
  const [verdict, setVerdict] = useState<Verdict | "ALL">("ALL");
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState("");

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setErr(String(e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    let r = data.stocks;
    if (verdict !== "ALL") r = r.filter((x) => x.verdict === verdict);
    if (q) r = r.filter((x) => x.symbol.toLowerCase().includes(q.toLowerCase()) || (x.name || "").toLowerCase().includes(q.toLowerCase()));
    if (minScore) r = r.filter((x) => (x.composite_score ?? -1) >= Number(minScore));
    const sorted = [...r].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
      return dir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [data, verdict, q, minScore, sortKey, dir]);

  if (err) return <Error msg={err} />;
  if (!data) return <Loading />;

  const counts = data.stocks.reduce((m: any, r) => ((m[r.verdict] = (m[r.verdict] || 0) + 1), m), {});
  const setSort = (k: string) => {
    if (k === sortKey) setDir(dir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setDir("desc"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Signal Dashboard</h1>
          <p className="text-sm text-slate-400">All available data per watchlist stock — sort any column, filter by signal/score.</p>
        </div>
        <div className="flex items-center gap-4">
          {data.fii_dii && (
            <div className="text-xs text-slate-400">
              FII <span className={Number(data.fii_dii.fii_net) >= 0 ? "text-buy" : "text-sell"}>{Number(data.fii_dii.fii_net) >= 0 ? "▲" : "▼"} {fmt.num(Number(data.fii_dii.fii_net), 0)}</span>
              {" · "}DII <span className={Number(data.fii_dii.dii_net) >= 0 ? "text-buy" : "text-sell"}>{Number(data.fii_dii.dii_net) >= 0 ? "▲" : "▼"} {fmt.num(Number(data.fii_dii.dii_net), 0)}</span>
            </div>
          )}
          <LastUpdated page="dashboard" />
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setVerdict(f)}
            className={`px-3 py-1 rounded-md text-xs ${verdict === f ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
            {f}{f !== "ALL" && counts[f] ? ` (${counts[f]})` : ""}
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symbol…"
          className="bg-ink border border-edge rounded-md px-3 py-1 text-xs outline-none focus:border-indigo-500" />
        <input value={minScore} onChange={(e) => setMinScore(e.target.value)} placeholder="Min score" type="number"
          className="w-24 bg-ink border border-edge rounded-md px-3 py-1 text-xs outline-none focus:border-indigo-500" />
        <span className="text-xs text-slate-500">{rows.length} stocks</span>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth: 1400 }}>
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} onClick={() => setSort(c.key)}
                  className={`th cursor-pointer select-none hover:text-slate-200 ${c.num ? "text-right" : ""} ${sortKey === c.key ? "text-indigo-300" : ""}`}>
                  {c.label}{sortKey === c.key ? (dir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.stock_id} className="hover:bg-edge/30">
                {cols.map((c) => (
                  <td key={c.key} className={`td ${c.num ? "text-right tabular-nums" : ""} ${c.cls ? c.cls(r[c.key], r) : ""}`}>
                    {c.render ? c.render(r) : (r[c.key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-500">P/E %ile: percentile of current P/E vs the stock's own ~5yr history (green ≤25 cheap, red ≥75 expensive). Insider: buys/sells in last 30 days.</p>
    </div>
  );
}

function sentCls(s: string) {
  return s === "positive" ? "text-buy" : s === "negative" ? "text-sell" : "text-slate-400";
}

export function Loading() {
  return <div className="text-slate-400 text-sm py-12 text-center">Loading…</div>;
}
export function Error({ msg }: { msg: string }) {
  return <div className="card p-4 text-sm text-sell">Failed to load: {msg}. Is the backend running on :8009?</div>;
}
