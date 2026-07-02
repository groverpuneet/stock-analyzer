import { useState, useEffect, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import MarketBadge from "./MarketBadge";

export interface Column {
  key: string;
  label: string;
  sortable?: boolean;
  width?: number;
  hidden?: boolean;
  format?: (val: any, row: any) => React.ReactNode;
}

interface DataTableProps {
  table: string;
  title: string;
  columns?: Column[];
  defaultSort?: string;
  defaultDir?: "asc" | "desc";
  stockFilter?: number;
  // Augmentation (Session M — data vintage):
  banner?: React.ReactNode;                       // warning/note rendered above the table
  extraColumns?: Column[];                         // computed columns prepended to the DB columns
  cellOverrides?: Record<string, (val: any, row: any) => React.ReactNode>; // per-key cell formatters
}

// ── Date/vintage helpers (exported for RawData per-slug config) ──────────────────
export function daysAgo(val: string | null): number | null {
  if (!val) return null;
  const d = new Date(val);
  if (isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

export function relTime(val: string | null): string {
  const n = daysAgo(val);
  if (n === null) return "—";
  if (n < 0) return "in " + (-n) + "d";
  if (n === 0) return "today";
  if (n === 1) return "1 day ago";
  return `${n} days ago`;
}

// "2026Q1" -> "Q1 2026"
export function quarterLabel(q: string | null): string {
  if (!q) return "—";
  const m = /^(\d{4})Q([1-4])$/.exec(q);
  return m ? `Q${m[2]} ${m[1]}` : q;
}

const _FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Indian fiscal-year quarter from a quarter-end date. FY runs Apr–Mar; FY26 = Apr'25–Mar'26.
// e.g. 2026-03-31 -> "Q4 FY26 (Jan–Mar 2026)"
export function fyQuarterLabel(val: string | null): string {
  if (!val) return "—";
  const d = new Date(val);
  if (isNaN(d.getTime())) return "—";
  const mo = d.getMonth(); // 0-11
  const yr = d.getFullYear();
  let q: number, fy: number, span: string;
  if (mo <= 2) { q = 4; fy = yr; span = `Jan–Mar ${yr}`; }
  else if (mo <= 5) { q = 1; fy = yr + 1; span = `Apr–Jun ${yr}`; }
  else if (mo <= 8) { q = 2; fy = yr + 1; span = `Jul–Sep ${yr}`; }
  else { q = 3; fy = yr + 1; span = `Oct–Dec ${yr}`; }
  return `Q${q} FY${String(fy).slice(2)} (${span})`;
}

// "2026-06-01" -> "June 2026"
export function monthLabel(val: string | null): string {
  if (!val) return "—";
  const d = new Date(val);
  if (isNaN(d.getTime())) return "—";
  return `${_FULL_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

// Freshness colour by age in days: green (current) / yellow (recent) / red (stale).
export function freshnessClass(days: number | null, greenMax = 45, yellowMax = 135): string {
  if (days === null) return "text-slate-400";
  if (days <= greenMax) return "text-buy";
  if (days <= yellowMax) return "text-watch";
  return "text-sell";
}

const STORAGE_KEY_PREFIX = "data-table-cols-";

function formatDate(val: string | null): string {
  if (!val) return "—";
  const d = new Date(val);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${d.getDate().toString().padStart(2, "0")}-${months[d.getMonth()]}-${d.getFullYear()}`;
}

function formatNumber(val: number | null, decimals = 2): string {
  if (val === null || val === undefined) return "—";
  return val.toLocaleString("en-IN", { maximumFractionDigits: decimals });
}

function formatValue(val: any, key: string): React.ReactNode {
  if (val === null || val === undefined) return <span className="text-slate-500">—</span>;

  // Market / exchange columns -> flag badge (India vs US demarcation)
  if ((key === "exchange" || key === "market") && typeof val === "string") {
    return <MarketBadge exchange={val} />;
  }

  // Date columns
  if (key.includes("date") || key.includes("_at") || key === "period_end" || key === "quarter_end" || key === "month") {
    return formatDate(val);
  }

  // Sentiment score coloring
  if (key === "sentiment_score" && typeof val === "number") {
    const color = val > 0.3 ? "text-buy" : val < -0.3 ? "text-sell" : "text-slate-300";
    return <span className={color}>{val.toFixed(3)}</span>;
  }

  // Percentage columns
  if (key.includes("_pct") || key.includes("percent") || key === "coverage_pct") {
    return typeof val === "number" ? `${formatNumber(val)}%` : val;
  }

  // Number columns
  if (typeof val === "number") {
    return formatNumber(val);
  }

  // Signal/verdict coloring
  if (key === "signal" || key === "verdict" || key === "status") {
    const colorMap: Record<string, string> = {
      BUY: "text-buy",
      SELL: "text-sell",
      WATCH: "text-watch",
      success: "text-buy",
      error: "text-sell",
      failed: "text-sell",
      running: "text-watch",
      partial: "text-watch",
    };
    return <span className={colorMap[val] || "text-slate-300"}>{val}</span>;
  }

  // URLs
  if (typeof val === "string" && val.startsWith("http")) {
    return (
      <a href={val} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline truncate max-w-48 inline-block">
        link
      </a>
    );
  }

  // Long text truncation
  if (typeof val === "string" && val.length > 100) {
    return <span title={val}>{val.slice(0, 100)}...</span>;
  }

  return String(val);
}

export default function DataTable({ table, title, columns: propColumns, defaultSort, defaultDir = "desc", stockFilter, banner, extraColumns, cellOverrides }: DataTableProps) {
  const [data, setData] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [dataAsOf, setDataAsOf] = useState<string | null>(null);
  const [nextRefresh, setNextRefresh] = useState<string | null>(null);
  const [dbColumns, setDbColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Query state
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [sortBy, setSortBy] = useState(defaultSort || "");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(defaultDir);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  // Column visibility (localStorage)
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_PREFIX + table);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });
  const [showColMenu, setShowColMenu] = useState(false);

  // Build columns from DB schema or props
  const columns: Column[] = useMemo(() => {
    if (propColumns) return propColumns;
    const auto = dbColumns.map((key) => ({
      key,
      label: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      sortable: true,
    }));
    // Computed/vintage columns (not sortable — they don't exist in the DB) go first.
    return [...(extraColumns ?? []), ...auto];
  }, [propColumns, dbColumns, extraColumns]);

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: perPage.toString(),
        sort_dir: sortDir,
      });
      if (sortBy) params.append("sort_by", sortBy);
      if (dateFrom) params.append("date_from", dateFrom);
      if (dateTo) params.append("date_to", dateTo);
      if (search) params.append("search", search);
      if (stockFilter) params.append("filter_stock", stockFilter.toString());

      const url = `/api/data/${table}?${params}`;
      console.log("[DataTable] Fetching:", url);
      const res = await fetch(url);
      console.log("[DataTable] Response status:", res.status);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const json = await res.json();
      console.log("[DataTable] Data received:", json.total_count, "rows");

      setData(json.data);
      setTotalCount(json.total_count);
      setTotalPages(json.total_pages);
      setLastUpdated(json.last_updated);
      setDataAsOf(json.data_as_of ?? null);
      setNextRefresh(json.next_refresh ?? null);
      setDbColumns(json.columns);
    } catch (e: any) {
      console.error("[DataTable] Error:", e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [table, page, perPage, sortBy, sortDir, dateFrom, dateTo, search, stockFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Save hidden cols to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_PREFIX + table, JSON.stringify([...hiddenCols]));
  }, [hiddenCols, table]);

  // Export CSV
  const exportCsv = () => {
    const params = new URLSearchParams();
    if (dateFrom) params.append("date_from", dateFrom);
    if (dateTo) params.append("date_to", dateTo);
    if (search) params.append("search", search);
    if (stockFilter) params.append("filter_stock", stockFilter.toString());
    window.open(`/api/data/${table}/export?${params}`, "_blank");
  };

  // Toggle column visibility
  const toggleCol = (key: string) => {
    setHiddenCols((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Handle sort
  const handleSort = (key: string) => {
    if (sortBy === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
    setPage(1);
  };

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset page on filter change
  useEffect(() => {
    setPage(1);
  }, [search, dateFrom, dateTo]);

  const visibleColumns = columns.filter((c) => !hiddenCols.has(c.key));

  // Debug logging
  console.log("[DataTable] table:", table, "columns:", columns.length, "visible:", visibleColumns.length, "data:", data.length);

  return (
    <div className="space-y-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{title}</h1>
          <div className="text-sm text-slate-400">
            {formatNumber(totalCount, 0)} rows
          </div>
          {/* Data freshness: most-recent data date · when the collector last ran · next run */}
          <div className="text-xs text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
            {dataAsOf && <span>📅 Data as of: <span className="text-slate-300">{formatDate(dataAsOf)}</span></span>}
            {lastUpdated && <span>🔄 Last refreshed: <span className="text-slate-300">{formatDate(lastUpdated)}</span> ({relTime(lastUpdated)})</span>}
            {nextRefresh && <span>⏭ Next refresh: <span className="text-slate-300">{formatDate(nextRefresh)}</span></span>}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <input
            type="text"
            placeholder="Search..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200 w-48 focus:outline-none focus:border-blue-500"
          />

          {/* Date filters */}
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="px-2 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200 focus:outline-none focus:border-blue-500"
          />
          <span className="text-slate-500">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="px-2 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200 focus:outline-none focus:border-blue-500"
          />

          {/* Column toggle */}
          <div className="relative">
            <button
              onClick={() => setShowColMenu(!showColMenu)}
              className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              Columns ▾
            </button>
            {showColMenu && (
              <div className="absolute right-0 top-full mt-1 w-56 max-h-80 overflow-auto bg-ink border border-edge rounded shadow-lg z-50">
                {columns.map((c) => (
                  <label key={c.key} className="flex items-center gap-2 px-3 py-1.5 hover:bg-edge cursor-pointer text-sm">
                    <input type="checkbox" checked={!hiddenCols.has(c.key)} onChange={() => toggleCol(c.key)} />
                    <span className="text-slate-300">{c.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Export */}
          <button onClick={exportCsv} className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-500">
            Export CSV
          </button>
        </div>
      </div>

      {/* Optional per-page banner (data-vintage / regulatory caveat) */}
      {banner && <div className="shrink-0">{banner}</div>}

      {/* Table */}
      <div className="overflow-auto border border-edge rounded flex-1 min-h-0">
        <table className="w-full text-sm">
          <thead className="bg-edge text-slate-300 sticky top-0">
            <tr>
              {visibleColumns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                  className={`px-3 py-2 text-left whitespace-nowrap ${col.sortable !== false ? "cursor-pointer hover:bg-slate-700" : ""}`}
                  style={col.width ? { width: col.width } : undefined}
                >
                  {col.label}
                  {sortBy === col.key && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={visibleColumns.length} className="px-3 py-8 text-center text-slate-400">
                  Loading...
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={visibleColumns.length} className="px-3 py-8 text-center text-sell">
                  Error: {error}
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={visibleColumns.length} className="px-3 py-8 text-center text-slate-400">
                  No data found
                </td>
              </tr>
            ) : (
              data.map((row, i) => (
                <tr key={i} className="border-t border-edge hover:bg-edge/50">
                  {visibleColumns.map((col) => (
                    <td key={col.key} className="px-3 py-2 whitespace-nowrap">
                      {col.key === "symbol" && row.stock_id ? (
                        <Link to={`/stock/${row.stock_id}`} className="text-blue-400 hover:underline">
                          {row[col.key]}
                        </Link>
                      ) : col.format ? (
                        col.format(row[col.key], row)
                      ) : cellOverrides?.[col.key] ? (
                        cellOverrides[col.key](row[col.key], row)
                      ) : (
                        formatValue(row[col.key], col.key)
                      )}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-slate-400 shrink-0">
        <div>
          Showing {((page - 1) * perPage) + 1}–{Math.min(page * perPage, totalCount)} of {formatNumber(totalCount, 0)}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage(1)}
            disabled={page === 1}
            className="px-2 py-1 rounded bg-edge disabled:opacity-50 hover:bg-slate-700"
          >
            ««
          </button>
          <button
            onClick={() => setPage(page - 1)}
            disabled={page === 1}
            className="px-2 py-1 rounded bg-edge disabled:opacity-50 hover:bg-slate-700"
          >
            «
          </button>
          <span>
            Page{" "}
            <input
              type="number"
              min={1}
              max={totalPages}
              value={page}
              onChange={(e) => {
                const v = parseInt(e.target.value);
                if (v >= 1 && v <= totalPages) setPage(v);
              }}
              className="w-12 px-1 py-0.5 text-center rounded bg-edge border border-slate-600 text-slate-200"
            />{" "}
            of {totalPages}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={page >= totalPages}
            className="px-2 py-1 rounded bg-edge disabled:opacity-50 hover:bg-slate-700"
          >
            »
          </button>
          <button
            onClick={() => setPage(totalPages)}
            disabled={page >= totalPages}
            className="px-2 py-1 rounded bg-edge disabled:opacity-50 hover:bg-slate-700"
          >
            »»
          </button>
        </div>
      </div>
    </div>
  );
}
