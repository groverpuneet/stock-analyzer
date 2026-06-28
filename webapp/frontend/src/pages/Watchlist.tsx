import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt } from "../api";
import SignalBadge from "../components/SignalBadge";
import { Loading, Error } from "./Dashboard";

export default function Watchlist() {
  const [names, setNames] = useState<string[]>([]);
  const [active, setActive] = useState("Default");
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<string>();

  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);

  const load = (name: string) => {
    setRows(null);
    api.watchlist(name).then(setRows).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    api.watchlistNames().then((n) => setNames(n.length ? n : ["Default"])).catch(() => setNames(["Default"]));
  }, []);
  useEffect(() => load(active), [active]);

  useEffect(() => {
    if (q.length < 1) return setResults([]);
    const t = setTimeout(() => api.search(q).then(setResults).catch(() => setResults([])), 200);
    return () => clearTimeout(t);
  }, [q]);

  async function add(stockId: number) {
    const r = await api.addWatchlist(stockId, active);
    if (r.ok || r.status === 409) {
      setQ("");
      setResults([]);
      load(active);
    }
  }
  async function remove(entryId: number) {
    await api.removeWatchlist(entryId);
    load(active);
  }

  if (err) return <Error msg={err} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Watchlist Manager</h1>
          <p className="text-sm text-slate-400">Track symbols across named lists. Public market data only — no holdings or P&L.</p>
        </div>
        <div className="flex gap-1">
          {names.map((n) => (
            <button
              key={n}
              onClick={() => setActive(n)}
              className={`px-3 py-1.5 rounded-md text-sm ${active === n ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"}`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Add box */}
      <div className="card p-4 relative">
        <div className="stat-label mb-1">Add a stock to “{active}”</div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search symbol or company…"
          className="w-full bg-ink border border-edge rounded-md px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        {results.length > 0 && (
          <div className="absolute z-10 left-4 right-4 mt-1 card max-h-72 overflow-y-auto">
            {results.map((s) => (
              <button
                key={s.id}
                onClick={() => add(s.id)}
                className="w-full text-left px-3 py-2 hover:bg-edge/50 flex justify-between items-center"
              >
                <span><span className="font-medium text-slate-100">{s.symbol}</span> <span className="text-xs text-slate-500">{s.name}</span></span>
                <span className="text-xs text-indigo-300">+ add</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {!rows ? (
        <Loading />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead>
              <tr>
                <th className="th">Symbol</th><th className="th">Verdict</th>
                <th className="th text-right">Price</th><th className="th text-right">RSI</th><th className="th"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entry_id} className="hover:bg-edge/30">
                  <td className="td">
                    <Link to={`/stock/${r.stock_id}`} className="font-medium text-indigo-300 hover:text-indigo-200">{r.symbol}</Link>
                    <div className="text-[11px] text-slate-500 truncate max-w-[200px]">{r.name}</div>
                  </td>
                  <td className="td">{r.verdict && <SignalBadge verdict={r.verdict} />}</td>
                  <td className="td text-right">{fmt.rupee(r.close)}</td>
                  <td className="td text-right">{fmt.num(r.rsi_14, 1)}</td>
                  <td className="td text-right">
                    <button onClick={() => remove(r.entry_id)} className="text-xs text-slate-500 hover:text-sell">remove</button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td className="td text-slate-500" colSpan={5}>No stocks in this list yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
