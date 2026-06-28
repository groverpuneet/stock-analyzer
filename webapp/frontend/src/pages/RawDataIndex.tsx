import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface TableInfo {
  name: string;
  columns: string[];
  row_count: number;
  has_stock: boolean;
  date_column: string | null;
  refresh_source: string | null;
}

// Categorized tables for navigation
const CATEGORIES: Record<string, { title: string; tables: string[] }> = {
  "market-data": {
    title: "Market Data",
    tables: ["daily_prices", "quotes", "technical_indicators", "fno_data", "expiry_calendar"],
  },
  fundamentals: {
    title: "Fundamentals",
    tables: ["fundamentals", "quarterly_financials", "earnings_calendar", "concall_transcripts"],
  },
  "flows-activity": {
    title: "Flows & Activity",
    tables: ["fii_dii_flows", "insider_trades", "bulk_deals", "sast_disclosures", "corporate_actions"],
  },
  "sentiment-news": {
    title: "Sentiment & News",
    tables: ["news_sentiment", "whatsapp_messages"],
  },
  institutional: {
    title: "Institutional",
    tables: ["institutional_holdings_13f", "mf_stock_holdings", "congress_trades", "analyst_targets", "tracked_filers"],
  },
  risk: {
    title: "Risk & Scores",
    tables: ["pledging_alerts", "shareholding_pattern", "stock_scores", "indicator_baselines"],
  },
  system: {
    title: "System",
    tables: ["stocks", "watchlist", "watchlist_changes", "macro_indicators", "data_refresh_log", "data_quality_log", "recompute_queue"],
  },
};

// Slug mapping
const TABLE_TO_SLUG: Record<string, string> = {
  analyst_targets: "analyst-targets",
  bulk_deals: "bulk-deals",
  concall_transcripts: "concalls",
  congress_trades: "congress-trades",
  corporate_actions: "corporate-actions",
  daily_prices: "prices",
  data_quality_log: "data-quality",
  data_refresh_log: "refresh-log",
  earnings_calendar: "earnings",
  expiry_calendar: "expiry-calendar",
  fii_dii_flows: "fii-dii",
  fno_data: "fno",
  fundamentals: "fundamentals",
  indicator_baselines: "indicator-baselines",
  insider_trades: "insider-trades",
  institutional_holdings_13f: "13f",
  macro_indicators: "macro",
  mf_stock_holdings: "mf-holdings",
  news_sentiment: "news",
  pledging_alerts: "pledging",
  quarterly_financials: "quarterly-financials",
  quotes: "quotes",
  recompute_queue: "recompute-queue",
  sast_disclosures: "sast",
  shareholding_pattern: "shareholding",
  stock_scores: "stock-scores",
  stocks: "stocks",
  technical_indicators: "technicals",
  tracked_filers: "tracked-filers",
  watchlist: "watchlist",
  watchlist_changes: "watchlist-changes",
  whatsapp_messages: "whatsapp",
};

function formatNumber(n: number): string {
  return n.toLocaleString("en-IN");
}

export default function RawDataIndex() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/data/tables")
      .then((r) => r.json())
      .then((d) => setTables(d.tables))
      .finally(() => setLoading(false));
  }, []);

  const tableMap = Object.fromEntries(tables.map((t) => [t.name, t]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Raw Data Tables</h1>
        <p className="text-slate-400 text-sm mt-1">
          Browse all {tables.length} database tables with full read access. Click any table to view, sort, filter, and export data.
        </p>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading tables...</div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(CATEGORIES).map(([key, cat]) => (
            <div key={key} className="border border-edge rounded-lg overflow-hidden">
              <div className="bg-edge px-4 py-2 text-slate-200 font-medium">{cat.title}</div>
              <div className="divide-y divide-edge">
                {cat.tables.map((tableName) => {
                  const info = tableMap[tableName];
                  const slug = TABLE_TO_SLUG[tableName];
                  if (!info || !slug) return null;
                  return (
                    <Link
                      key={tableName}
                      to={`/data/${slug}`}
                      className="flex items-center justify-between px-4 py-2 hover:bg-edge/50 transition-colors"
                    >
                      <span className="text-slate-300">{tableName.replace(/_/g, " ")}</span>
                      <span className="text-sm text-slate-500">{formatNumber(info.row_count)} rows</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Summary stats */}
      {!loading && (
        <div className="mt-8 p-4 border border-edge rounded-lg">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-slate-100">{tables.length}</div>
              <div className="text-sm text-slate-400">Tables</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-100">
                {formatNumber(tables.reduce((sum, t) => sum + t.row_count, 0))}
              </div>
              <div className="text-sm text-slate-400">Total Rows</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-100">
                {formatNumber(tables.reduce((sum, t) => sum + t.columns.length, 0))}
              </div>
              <div className="text-sm text-slate-400">Total Columns</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-100">
                {tables.filter((t) => t.has_stock).length}
              </div>
              <div className="text-sm text-slate-400">Stock-linked Tables</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
