import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt } from "../api";
import SignalBadge from "../components/SignalBadge";
import MarketBadge from "../components/MarketBadge";
import { Loading, Error as ErrorView } from "./Dashboard";
import LastUpdated from "../components/LastUpdated";
import RefreshAll from "../components/RefreshAll";
import { PAGE_ASSETS } from "../lib/refreshTargets";

interface SearchResult {
  id?: number;          // present for local (NSE + seeded US) rows
  ticker?: string;      // present for Polygon-only US rows
  symbol: string;
  name: string;
  exchange: string;
}

export default function Watchlist() {
  const [names, setNames] = useState<string[]>([]);
  const [active, setActive] = useState("Default");
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<string>();

  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [addingKey, setAddingKey] = useState<string | null>(null);
  const [addMsg, setAddMsg] = useState<string>("");

  const load = (name: string) => {
    setRows(null);
    api.watchlist(name).then(setRows).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    api.watchlistNames().then((n) => setNames(n.length ? n : ["Default"])).catch(() => setNames(["Default"]));
  }, []);
  useEffect(() => load(active), [active]);

  useEffect(() => {
    if (q.length < 1) { setResults([]); return; }
    setSearching(true);
    const t = setTimeout(async () => {
      // Search NSE + seeded US (local) and new US tickers (Polygon) simultaneously.
      const [local, us] = await Promise.all([
        api.search(q).catch(() => []),
        api.usStockSearch(q).catch(() => []),
      ]);
      const seen = new Set((local as any[]).map((r) => r.symbol.toUpperCase()));
      const merged: SearchResult[] = [
        ...(local as any[]),
        ...(us as any[]).filter((r) => !seen.has(r.symbol.toUpperCase())),
      ];
      setResults(merged);
      setSearching(false);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function add(s: SearchResult) {
    const key = s.symbol;
    setAddingKey(key);
    setAddMsg("");
    try {
      if (s.id != null) {
        const r = await api.addWatchlist(s.id, active);
        if (!r.ok && r.status !== 409) throw new Error(`add failed (${r.status})`);
      } else {
        // New US ticker — creates stock, fetches 2yr OHLCV + indicators (a few seconds).
        setAddMsg(`Fetching 2yr history for ${s.symbol}…`);
        const r = await api.addUsStock(s.ticker || s.symbol, active);
        if (!r.ok && r.status !== 409) {
          const d = await r.json().catch(() => ({}));
          throw new Error(d.detail || `add failed (${r.status})`);
        }
      }
      setQ("");
      setResults([]);
      setAddMsg("");
      load(active);
    } catch (e: any) {
      setAddMsg(e.message || "Failed to add");
    } finally {
      setAddingKey(null);
    }
  }
  async function remove(entryId: number) {
    await api.removeWatchlist(entryId);
    load(active);
  }

  if (err) return <ErrorView msg={err} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Watchlist Manager</h1>
          <p className="text-sm text-slate-400">Track symbols across named lists — 🇮🇳 NSE + 🇺🇸 US. Public market data only, no holdings or P&L.</p>
          <div className="mt-1 flex items-center gap-3">
            <LastUpdated page="watchlist" />
            <RefreshAll assets={PAGE_ASSETS.watchlist} onDone={() => load(active)} />
          </div>
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
        <div className="stat-label mb-1">Add a stock to “{active}” — search NSE &amp; US together</div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search symbol or company… (e.g. SBIN, MELI, NVDA)"
          className="w-full bg-ink border border-edge rounded-md px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        {addMsg && <div className="text-xs text-indigo-300 mt-1">{addMsg}</div>}
        {q.length >= 1 && (results.length > 0 || searching) && (
          <div className="absolute z-10 left-4 right-4 mt-1 card max-h-72 overflow-y-auto">
            {searching && results.length === 0 && (
              <div className="px-3 py-2 text-xs text-slate-500">Searching NSE &amp; US…</div>
            )}
            {results.map((s) => {
              const key = (s.id != null ? `l${s.id}` : `u${s.ticker}`);
              return (
                <button
                  key={key}
                  disabled={addingKey === s.symbol}
                  onClick={() => add(s)}
                  className="w-full text-left px-3 py-2 hover:bg-edge/50 flex justify-between items-center disabled:opacity-50"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <MarketBadge exchange={s.exchange} />
                    <span className="font-medium text-slate-100">{s.symbol}</span>
                    <span className="text-xs text-slate-500 truncate">{s.name}</span>
                  </span>
                  <span className="text-xs text-indigo-300 whitespace-nowrap">
                    {addingKey === s.symbol ? "adding…" : s.id != null ? "+ add" : "+ add (US)"}
                  </span>
                </button>
              );
            })}
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
                <th className="th">Symbol</th><th className="th">Market</th><th className="th">Verdict</th>
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
                  <td className="td"><MarketBadge exchange={r.exchange} /></td>
                  <td className="td">{r.verdict && <SignalBadge verdict={r.verdict} />}</td>
                  <td className="td text-right">{isUS(r.exchange) ? fmt.num(r.close) : fmt.rupee(r.close)}</td>
                  <td className="td text-right">{fmt.num(r.rsi_14, 1)}</td>
                  <td className="td text-right">
                    <button onClick={() => remove(r.entry_id)} className="text-xs text-slate-500 hover:text-sell">remove</button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td className="td text-slate-500" colSpan={6}>No stocks in this list yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function isUS(exchange?: string) {
  return exchange === "NYSE" || exchange === "NASDAQ";
}
