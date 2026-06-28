// Typed client for the Stock Analyzer API. All data is real (PostgreSQL).

export type Verdict = "BUY" | "SELL" | "WATCH" | "NEUTRAL";

export interface SignalRow {
  stock_id: number;
  symbol: string;
  name: string;
  exchange: string;
  date: string | null;
  close: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  sma_50: number | null;
  sma_200: number | null;
  verdict: Verdict;
  signals: { type: string; signal: string; strength: string; message: string }[];
}

export interface SignalsResponse {
  signals: SignalRow[];
  counts: Record<Verdict, number>;
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

interface DataTableParams {
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  filter_stock?: number;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export const api = {
  // Raw data tables
  dataTables: () => get<{ tables: any[] }>("/api/data/tables"),
  dataTable: (table: string, params: DataTableParams = {}) => {
    const p = new URLSearchParams();
    if (params.page) p.append("page", params.page.toString());
    if (params.per_page) p.append("per_page", params.per_page.toString());
    if (params.sort_by) p.append("sort_by", params.sort_by);
    if (params.sort_dir) p.append("sort_dir", params.sort_dir);
    if (params.filter_stock) p.append("filter_stock", params.filter_stock.toString());
    if (params.date_from) p.append("date_from", params.date_from);
    if (params.date_to) p.append("date_to", params.date_to);
    if (params.search) p.append("search", params.search);
    return get<any>(`/api/data/${table}?${p}`);
  },
  signals: (verdict?: string) =>
    get<SignalsResponse>(`/api/signals${verdict ? `?verdict=${verdict}` : ""}`),
  stock: (id: number) => get<any>(`/api/stocks/${id}`),
  search: (q: string) => get<any[]>(`/api/stocks/search?q=${encodeURIComponent(q)}`),
  macro: () => get<any>("/api/macro"),
  watchlist: (name = "Default") => get<any[]>(`/api/watchlist?name=${encodeURIComponent(name)}`),
  watchlistNames: () => get<string[]>("/api/watchlist/names"),
  addWatchlist: (stock_id: number, name: string) =>
    fetch("/api/watchlist", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ stock_id, name }),
    }),
  removeWatchlist: (entryId: number) =>
    fetch(`/api/watchlist/${entryId}`, { method: "DELETE" }),
  opportunities: () => get<any>("/api/opportunities"),
  lastUpdated: (page: string) => get<any>(`/api/refresh/last?page=${page}`),
  refreshSources: () => get<any>("/api/refresh/sources"),
  refreshStatus: () => get<any>("/api/refresh/status"),
  trigger: (source: string) =>
    fetch("/api/refresh/trigger", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source }),
    }).then((r) => r.json()),
  runStatus: (runId: string) => get<any>(`/api/refresh/run-status?run_id=${runId}`),
  dashboard: () => get<any>("/api/dashboard"),
  peHistory: (id: number) => get<any>(`/api/stocks/${id}/pe-history`),
  triggerAll: () => fetch("/api/refresh/trigger-all", { method: "POST" }).then((r) => r.json()),
  triggerFailed: () => fetch("/api/refresh/trigger-failed", { method: "POST" }).then((r) => r.json()),
  triggerFull: () => fetch("/api/refresh/trigger-full", { method: "POST" }).then((r) => r.json()),
  qualityHealth: () => get<any>("/api/quality/health"),
  fearGreed: () => get<FearGreed>("/api/macro/fear-greed"),
  quarterlyResults: (id: number) => get<any>(`/api/stocks/${id}/quarterly-results`),
  financials: (id: number) => get<any>(`/api/stocks/${id}/financials`),
  concalls: (id: number) => get<any>(`/api/stocks/${id}/concalls`),
};

export interface FearGreedMarket {
  score: number | null;
  rating: string | null;
  date: string | null;
  history: { date: string; value: number }[];
}
export interface FearGreed {
  india: FearGreedMarket;
  us: FearGreedMarket;
}

// Fear & Greed score 0-100 -> color
export function fgColor(v: number | null | undefined): string {
  if (v == null) return "#64748b";
  if (v < 25) return "#ef4444"; // extreme fear - red
  if (v < 45) return "#f97316"; // fear - orange
  if (v < 55) return "#eab308"; // neutral - yellow
  if (v < 75) return "#84cc16"; // greed - lime
  return "#22c55e"; // extreme greed - green
}

// completeness 0-100 -> tailwind text color (green >90, yellow 70-90, red <70)
export function completenessClass(v: number | null | undefined): string {
  if (v == null) return "text-slate-500";
  if (v >= 90) return "text-buy";
  if (v >= 70) return "text-watch";
  return "text-sell";
}

// "2026-06-28T04:03:50" -> "2h ago" / "3d ago"
export function relTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export const statusClass: Record<string, string> = {
  success: "bg-buy/15 text-buy border-buy/30",
  error: "bg-sell/15 text-sell border-sell/30",
  failed: "bg-sell/15 text-sell border-sell/30",
  running: "bg-watch/15 text-watch border-watch/30",
  never_run: "bg-slate-600/15 text-slate-400 border-slate-600/30",
};

export const fmt = {
  num: (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: d }),
  pct: (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "—" : `${v.toFixed(d)}%`,
  rupee: (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "—" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: d })}`,
};

export const verdictClass: Record<Verdict, string> = {
  BUY: "bg-buy/15 text-buy border-buy/30",
  SELL: "bg-sell/15 text-sell border-sell/30",
  WATCH: "bg-watch/15 text-watch border-watch/30",
  NEUTRAL: "bg-slate-600/15 text-slate-400 border-slate-600/30",
};
