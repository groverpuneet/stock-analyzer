import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt, Verdict, completenessClass } from "../api";
import SignalBadge from "../components/SignalBadge";
import LastUpdated from "../components/LastUpdated";
import FearGreedWidget from "../components/FearGreedWidget";

type Row = Record<string, any>;
type Dir = "asc" | "desc";

// Column definitions for the expanded dashboard table.
interface Col {
  key: string;
  label: string;
  render?: (r: Row) => any;
  num?: boolean;            // numeric sort + right align
  cls?: (v: any, r: Row) => string;
  width?: number;           // default width (px)
}

const cols: Col[] = [
  { key: "symbol", label: "Symbol", width: 90, render: (r) => (
      <Link to={`/stock/${r.stock_id}`} className="font-medium text-indigo-300 hover:text-indigo-200">{r.symbol}</Link>
    ) },
  { key: "industry", label: "Industry", width: 150, render: (r) => (
      <span className="text-slate-300 text-xs" title={r.sector || ""}>{r.industry || "—"}</span>
    ) },
  { key: "verdict", label: "Signal", width: 90, render: (r) => <SignalBadge verdict={r.verdict as Verdict} /> },
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
  { key: "completeness", label: "Quality", num: true, render: (r) => r.completeness == null ? "—" : `${r.completeness.toFixed(0)}%`,
    cls: (v) => completenessClass(v) },
];

const COL_MAP: Record<string, Col> = Object.fromEntries(cols.map((c) => [c.key, c]));
const DEFAULT_ORDER = cols.map((c) => c.key);
const FILTERS: (Verdict | "ALL")[] = ["ALL", "BUY", "SELL", "WATCH", "NEUTRAL"];

// localStorage keys for column customization (Part 11)
const LS_ORDER = "dash.colOrder";
const LS_HIDDEN = "dash.colHidden";
const LS_WIDTHS = "dash.colWidths";

function loadLS<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}

export default function Dashboard() {
  const [data, setData] = useState<{ stocks: Row[]; fii_dii: any } | null>(null);
  const [err, setErr] = useState<string>();
  const [sortKey, setSortKey] = useState("composite_score");
  const [dir, setDir] = useState<Dir>("desc");
  const [verdict, setVerdict] = useState<Verdict | "ALL">("ALL");
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState("");

  // ---- column customization state (persisted to localStorage) ----
  const [order, setOrder] = useState<string[]>(() => {
    const saved = loadLS<string[]>(LS_ORDER, DEFAULT_ORDER);
    // keep only known keys + append any new columns added since last save
    const known = saved.filter((k) => COL_MAP[k]);
    return [...known, ...DEFAULT_ORDER.filter((k) => !known.includes(k))];
  });
  const [hidden, setHidden] = useState<string[]>(() => loadLS<string[]>(LS_HIDDEN, []));
  const [widths, setWidths] = useState<Record<string, number>>(() => loadLS<Record<string, number>>(LS_WIDTHS, {}));
  const [showCols, setShowCols] = useState(false);
  const dragKey = useRef<string | null>(null);

  useEffect(() => { localStorage.setItem(LS_ORDER, JSON.stringify(order)); }, [order]);
  useEffect(() => { localStorage.setItem(LS_HIDDEN, JSON.stringify(hidden)); }, [hidden]);
  useEffect(() => { localStorage.setItem(LS_WIDTHS, JSON.stringify(widths)); }, [widths]);

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setErr(String(e)));
  }, []);

  const visibleCols = useMemo(
    () => order.map((k) => COL_MAP[k]).filter((c) => c && !hidden.includes(c.key)),
    [order, hidden]
  );

  const rows = useMemo(() => {
    if (!data) return [];
    let r = data.stocks;
    if (verdict !== "ALL") r = r.filter((x) => x.verdict === verdict);
    if (q) r = r.filter((x) => x.symbol.toLowerCase().includes(q.toLowerCase()) || (x.name || "").toLowerCase().includes(q.toLowerCase()) || (x.industry || "").toLowerCase().includes(q.toLowerCase()));
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

  // ---- drag to reorder ----
  const onDrop = (target: string) => {
    const src = dragKey.current;
    dragKey.current = null;
    if (!src || src === target) return;
    setOrder((o) => {
      const next = o.filter((k) => k !== src);
      const idx = next.indexOf(target);
      next.splice(idx, 0, src);
      return next;
    });
  };

  // ---- resize ----
  const startResize = (key: string, e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX;
    const startW = widths[key] ?? COL_MAP[key].width ?? 80;
    const move = (ev: MouseEvent) => {
      const w = Math.max(48, startW + ev.clientX - startX);
      setWidths((prev) => ({ ...prev, [key]: w }));
    };
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const resetCols = () => { setOrder(DEFAULT_ORDER); setHidden([]); setWidths({}); };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Signal Dashboard</h1>
          <p className="text-sm text-slate-400">All available data per watchlist stock — sort, filter, drag/resize/hide columns.</p>
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

      <FearGreedWidget />

      {/* Filters + column controls */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setVerdict(f)}
            className={`px-3 py-1 rounded-md text-xs ${verdict === f ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
            {f}{f !== "ALL" && counts[f] ? ` (${counts[f]})` : ""}
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symbol/industry…"
          className="bg-ink border border-edge rounded-md px-3 py-1 text-xs outline-none focus:border-indigo-500" />
        <input value={minScore} onChange={(e) => setMinScore(e.target.value)} placeholder="Min score" type="number"
          className="w-24 bg-ink border border-edge rounded-md px-3 py-1 text-xs outline-none focus:border-indigo-500" />
        <span className="text-xs text-slate-500">{rows.length} stocks</span>
        <div className="relative ml-auto">
          <button onClick={() => setShowCols((s) => !s)}
            className="px-3 py-1 rounded-md text-xs border border-edge text-slate-300 hover:text-slate-100">
            ⚙ Columns
          </button>
          {showCols && (
            <div className="absolute right-0 mt-1 z-30 card p-2 w-56 max-h-80 overflow-y-auto shadow-xl">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-slate-400">Show / hide columns</span>
                <button onClick={resetCols} className="text-xs text-indigo-300 hover:text-indigo-200">Reset</button>
              </div>
              {DEFAULT_ORDER.map((k) => (
                <label key={k} className="flex items-center gap-2 py-0.5 text-xs text-slate-300 cursor-pointer hover:text-slate-100">
                  <input type="checkbox" checked={!hidden.includes(k)}
                    onChange={() => setHidden((h) => h.includes(k) ? h.filter((x) => x !== k) : [...h, k])} />
                  {COL_MAP[k].label}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="text-sm" style={{ tableLayout: "fixed", width: "max-content", minWidth: "100%" }}>
          <thead>
            <tr>
              {visibleCols.map((c) => {
                const w = widths[c.key] ?? c.width ?? 80;
                return (
                  <th key={c.key}
                    draggable
                    onDragStart={() => { dragKey.current = c.key; }}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => onDrop(c.key)}
                    onClick={() => setSort(c.key)}
                    style={{ width: w, minWidth: w, maxWidth: w }}
                    className={`th relative cursor-pointer select-none hover:text-slate-200 ${c.num ? "text-right" : ""} ${sortKey === c.key ? "text-indigo-300" : ""}`}
                    title="Click to sort · drag to reorder">
                    <span className="truncate inline-block align-bottom" style={{ maxWidth: w - 14 }}>
                      {c.label}{sortKey === c.key ? (dir === "asc" ? " ▲" : " ▼") : ""}
                    </span>
                    {/* resize handle */}
                    <span onMouseDown={(e) => startResize(c.key, e)} onClick={(e) => e.stopPropagation()}
                      className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-indigo-500/50" />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.stock_id} className="hover:bg-edge/30">
                {visibleCols.map((c) => {
                  const w = widths[c.key] ?? c.width ?? 80;
                  return (
                    <td key={c.key} style={{ width: w, minWidth: w, maxWidth: w }}
                      className={`td truncate ${c.num ? "text-right tabular-nums" : ""} ${c.cls ? c.cls(r[c.key], r) : ""}`}>
                      {c.render ? c.render(r) : (r[c.key] ?? "—")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-500">Drag column headers to reorder · drag the right edge to resize · ⚙ Columns to hide/show or reset. Layout is saved in your browser. P/E %ile: percentile of current P/E vs the stock's own ~5yr history.</p>
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
