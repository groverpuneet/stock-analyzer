import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt, SignalsResponse, Verdict } from "../api";
import SignalBadge from "../components/SignalBadge";

const FILTERS: (Verdict | "ALL")[] = ["ALL", "BUY", "SELL", "WATCH", "NEUTRAL"];

export default function Dashboard() {
  const [data, setData] = useState<SignalsResponse | null>(null);
  const [err, setErr] = useState<string>();
  const [filter, setFilter] = useState<Verdict | "ALL">("ALL");

  useEffect(() => {
    api.signals().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <Error msg={err} />;
  if (!data) return <Loading />;

  const rows = data.signals.filter((r) => filter === "ALL" || r.verdict === filter);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Signal Dashboard</h1>
        <p className="text-sm text-slate-400">
          BUY / SELL / WATCH across the watchlist, derived live from the latest technical indicators.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {(["BUY", "SELL", "WATCH", "NEUTRAL"] as Verdict[]).map((v) => (
          <button
            key={v}
            onClick={() => setFilter(filter === v ? "ALL" : v)}
            className={`card px-4 py-3 text-left ${filter === v ? "ring-1 ring-indigo-500" : ""}`}
          >
            <div className="stat-label">{v}</div>
            <div className="stat-value">{data.counts[v] ?? 0}</div>
          </button>
        ))}
      </div>

      <div className="flex gap-1">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-md text-xs ${
              filter === f ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[680px]">
          <thead>
            <tr>
              <th className="th">Symbol</th>
              <th className="th">Verdict</th>
              <th className="th text-right">Price</th>
              <th className="th text-right">RSI(14)</th>
              <th className="th text-right">MACD</th>
              <th className="th">Signals</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.stock_id} className="hover:bg-edge/30">
                <td className="td">
                  <Link to={`/stock/${r.stock_id}`} className="font-medium text-indigo-300 hover:text-indigo-200">
                    {r.symbol}
                  </Link>
                  <div className="text-[11px] text-slate-500 truncate max-w-[180px]">{r.name}</div>
                </td>
                <td className="td"><SignalBadge verdict={r.verdict} /></td>
                <td className="td text-right">{fmt.rupee(r.close)}</td>
                <td className="td text-right">
                  <span className={r.rsi_14 != null && r.rsi_14 < 30 ? "text-buy" : r.rsi_14 != null && r.rsi_14 > 70 ? "text-sell" : ""}>
                    {fmt.num(r.rsi_14, 1)}
                  </span>
                </td>
                <td className="td text-right">{fmt.num(r.macd, 2)}</td>
                <td className="td">
                  <div className="flex flex-wrap gap-1">
                    {r.signals.slice(0, 3).map((s, i) => (
                      <span key={i} className="text-[11px] bg-edge/60 rounded px-1.5 py-0.5 text-slate-300">
                        {s.message}
                      </span>
                    ))}
                    {r.signals.length === 0 && <span className="text-[11px] text-slate-500">—</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Loading() {
  return <div className="text-slate-400 text-sm py-12 text-center">Loading…</div>;
}
export function Error({ msg }: { msg: string }) {
  return (
    <div className="card p-4 text-sm text-sell">Failed to load: {msg}. Is the backend running on :8000?</div>
  );
}
