import { useState, useEffect, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";

interface Column {
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

export default function DataTable({ table, title, columns: propColumns, defaultSort, defaultDir = "desc", stockFilter }: DataTableProps) {
  const [data, setData] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
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
    return dbColumns.map((key) => ({
      key,
      label: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      sortable: true,
    }));
  }, [propColumns, dbColumns]);

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
            {lastUpdated && <span> · Last updated: {formatDate(lastUpdated)}</span>}
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
