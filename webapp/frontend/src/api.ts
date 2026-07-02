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

// Global 401 handler — AuthGate registers this so any expired/missing session
// (on any API call) flips the whole app back to the login screen.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

// credentials:"include" so the session cookie rides along (also works cross-origin,
// e.g. when the same backend is reached directly rather than via the Vite proxy).
async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "include" });
  if (r.status === 401) {
    onUnauthorized?.();
    throw new Error("401 Unauthorized");
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export interface AuthStatus {
  authenticated: boolean;
  username: string | null;
}

export const auth = {
  // public endpoint; auth_enabled tells us whether a login is required at all
  health: () => get<{ status: string; auth_enabled: boolean }>("/api/health"),
  status: () => get<AuthStatus>("/api/auth/status"),
  login: async (username: string, password: string) => {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.detail || `Login failed (${r.status})`);
    }
    return r.json() as Promise<{ status: string; username: string }>;
  },
  logout: () => fetch("/api/auth/logout", { method: "POST", credentials: "include" }),
};

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
  fiiDiiTrend: (limit = 30) => get<any>(`/api/macro/fii-dii-trend?limit=${limit}`),
  usStockSearch: (q: string) => get<any[]>(`/api/watchlist/search-us?q=${encodeURIComponent(q)}`),
  addUsStock: (ticker: string, name = "Default") =>
    fetch("/api/watchlist/add-us", {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ticker, name }),
    }),
  watchlist: (name = "Default") => get<any[]>(`/api/watchlist?name=${encodeURIComponent(name)}`),
  watchlistNames: () => get<string[]>("/api/watchlist/names"),
  addWatchlist: (stock_id: number, name: string) =>
    fetch("/api/watchlist", {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ stock_id, name }),
    }),
  removeWatchlist: (entryId: number) =>
    fetch(`/api/watchlist/${entryId}`, { method: "DELETE", credentials: "include" }),
  opportunities: () => get<any>("/api/opportunities"),
  lastUpdated: (page: string) => get<any>(`/api/refresh/last?page=${page}`),
  refreshLast: (sources: string) => get<any>(`/api/refresh/last?sources=${encodeURIComponent(sources)}`),
  refreshSources: () => get<any>("/api/refresh/sources"),
  refreshStatus: () => get<any>("/api/refresh/status"),
  trigger: (source: string) =>
    fetch("/api/refresh/trigger", {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source }),
    }).then((r) => r.json()),
  runStatus: (runId: string) => get<any>(`/api/refresh/run-status?run_id=${runId}`),
  dashboard: () => get<any>("/api/dashboard"),
  peHistory: (id: number) => get<any>(`/api/stocks/${id}/pe-history`),
  triggerAll: () => fetch("/api/refresh/trigger-all", { method: "POST", credentials: "include" }).then((r) => r.json()),
  triggerRegion: (region: string) =>
    fetch(`/api/refresh/trigger-region?region=${encodeURIComponent(region)}`, { method: "POST", credentials: "include" }).then((r) => r.json()),
  triggerFailed: () => fetch("/api/refresh/trigger-failed", { method: "POST", credentials: "include" }).then((r) => r.json()),
  // Generic Dagster materialization (used by all 🔄 refresh buttons)
  materialize: (body: { asset?: string; job?: string }) =>
    fetch("/api/dagster/materialize", {
      method: "POST", credentials: "include",
      headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }).then((r) => r.json()),
  dagsterRunStatus: (runId: string) => get<any>(`/api/dagster/run-status/${runId}`),
  triggerFull: () => fetch("/api/refresh/trigger-full", { method: "POST", credentials: "include" }).then((r) => r.json()),
  triggerAudit: () => fetch("/api/refresh/trigger-audit", { method: "POST", credentials: "include" }).then((r) => r.json()),
  refreshControl: () => get<any>("/api/refresh/control"),
  refreshHealth: () => get<any>("/api/refresh/health"),
  qualityHealth: () => get<any>("/api/quality/health"),
  qualityGaps: () => get<any>("/api/quality/gaps"),
  fearGreed: () => get<FearGreed>("/api/macro/fear-greed"),
  quarterlyResults: (id: number) => get<any>(`/api/stocks/${id}/quarterly-results`),
  financials: (id: number) => get<any>(`/api/stocks/${id}/financials`),
  concalls: (id: number) => get<any>(`/api/stocks/${id}/concalls`),
};

// ── Portfolio (private, localhost-only, TOTP-gated) ──────────────────────────
// Uses raw fetch (not `get`) so a portfolio 401/403 never triggers the global
// main-session logout — the portfolio gate is independent of the main session.
export const isLocalhost = () =>
  ["localhost", "127.0.0.1", "::1", "[::1]"].includes(window.location.hostname);

async function pget<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "include" });
  if (!r.ok) throw Object.assign(new Error(`${r.status}`), { status: r.status });
  return r.json();
}
function pjson(url: string, method: string, body?: any) {
  return fetch(url, {
    method, credentials: "include",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const portfolio = {
  status: () => pget<{ verified: boolean; ttl_seconds: number }>("/api/portfolio/status"),
  verifyTotp: (code: string) => pjson("/api/portfolio/verify-totp", "POST", { code }),
  logout: () => pjson("/api/portfolio/logout-totp", "POST"),
  preview: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/portfolio/preview", { method: "POST", credentials: "include", body: fd });
  },
  save: (rows: any[], replace: boolean) => pjson("/api/portfolio/save", "POST", { rows, replace }),
  holdings: () => pget<{ holdings: any[] }>("/api/portfolio/holdings"),
  summary: () => pget<any>("/api/portfolio/summary"),
  alerts: (notify = false) => pget<{ alerts: any[] }>(`/api/portfolio/alerts?notify=${notify}`),
  overlay: () => pget<{ overlay: Record<string, any> }>("/api/portfolio/signal-overlay"),
  updateHolding: (id: number, body: any) => pjson(`/api/portfolio/holding/${id}`, "PUT", body),
  deleteHolding: (id: number) => pjson(`/api/portfolio/holding/${id}`, "DELETE"),
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
  stalled: "bg-sell/15 text-sell border-sell/30",
  running: "bg-watch/15 text-watch border-watch/30",
  retrying: "bg-watch/15 text-watch border-watch/30",
  partial: "bg-watch/15 text-watch border-watch/30",
  pending: "bg-slate-600/15 text-slate-400 border-slate-600/30",
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
