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

export const api = {
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
