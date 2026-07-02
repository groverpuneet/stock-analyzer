import { useParams } from "react-router-dom";
import DataTable, {
  Column,
  quarterLabel,
  fyQuarterLabel,
  monthLabel,
  daysAgo,
  relTime,
  freshnessClass,
} from "../components/DataTable";

// ── small helpers ────────────────────────────────────────────────────────────
function diffDays(later: string | null, earlier: string | null): number | null {
  if (!later || !earlier) return null;
  const a = new Date(later), b = new Date(earlier);
  if (isNaN(a.getTime()) || isNaN(b.getTime())) return null;
  return Math.round((a.getTime() - b.getTime()) / 86_400_000);
}

function Banner({ tone = "warn", children }: { tone?: "warn" | "info"; children: React.ReactNode }) {
  const cls = tone === "warn"
    ? "bg-amber-500/10 border-amber-500/40 text-amber-200"
    : "bg-blue-500/10 border-blue-500/40 text-blue-200";
  return <div className={`text-xs rounded border px-3 py-2 ${cls}`}>{children}</div>;
}

const dim = "text-slate-500";

// ── per-slug enhancement config ──────────────────────────────────────────────
interface EnhancedConfig {
  table: string;
  title: string;
  banner?: React.ReactNode;
  extraColumns?: Column[];
  cellOverrides?: Record<string, (val: any, row: any) => React.ReactNode>;
}

const TABLE_CONFIG: Record<string, EnhancedConfig> = {
  "analyst-targets": { table: "analyst_targets", title: "Analyst Targets" },
  "bulk-deals": {
    table: "bulk_deals",
    title: "Bulk & Block Deals",
    extraColumns: [
      { key: "_age", label: "Age", sortable: false, format: (_v, r) => <span className={dim}>{relTime(r.date)}</span> },
    ],
  },
  "concalls": { table: "concall_transcripts", title: "Concall Transcripts" },
  "congress-trades": {
    table: "congress_trades",
    title: "Congress Trades",
    banner: <Banner>⚠️ US politicians must disclose trades within 45 days (STOCK Act). Rows disclosed &gt; 30 days after the trade are flagged.</Banner>,
    extraColumns: [
      { key: "_trade_age", label: "Trade Age", sortable: false, format: (_v, r) => <span className={dim}>{relTime(r.trade_date)}</span> },
    ],
    cellOverrides: {
      days_to_disclose: (v) =>
        v == null ? <span className={dim}>—</span>
          : <span className={v > 30 ? "text-sell font-medium" : "text-slate-300"}>{v}d{v > 30 ? " ⚠" : ""}</span>,
    },
  },
  "corporate-actions": { table: "corporate_actions", title: "Corporate Actions" },
  "prices": { table: "daily_prices", title: "Daily Prices" },
  "data-quality": { table: "data_quality_log", title: "Data Quality Log" },
  "refresh-log": { table: "data_refresh_log", title: "Data Refresh Log" },
  "earnings": { table: "earnings_calendar", title: "Earnings Calendar" },
  "expiry-calendar": { table: "expiry_calendar", title: "F&O Expiry Calendar" },
  "fii-dii": { table: "fii_dii_flows", title: "FII/DII Flows" },
  "fno": { table: "fno_data", title: "F&O Data" },
  "fundamentals": { table: "fundamentals", title: "Fundamentals" },
  "indicator-baselines": { table: "indicator_baselines", title: "Indicator Baselines" },
  "insider-trades": {
    table: "insider_trades",
    title: "Insider Trades",
    banner: (
      <Banner>
        📅 <b>date</b> is the transaction date. Disclosure date / days-to-disclose aren&apos;t captured yet
        (the SEC Form 4 &amp; NSE collectors store only the transaction date) — see the follow-up note.
      </Banner>
    ),
    extraColumns: [
      { key: "_age", label: "Age", sortable: false, format: (_v, r) => <span className={dim}>{relTime(r.date)}</span> },
    ],
  },
  "13f": {
    table: "institutional_holdings_13f",
    title: "SEC 13F Holdings",
    banner: <Banner>⚠️ 13F data reflects holdings <b>as of quarter end</b>. Funds have up to 45 days to file after quarter end, so positions may have changed.</Banner>,
    extraColumns: [
      { key: "_filed_ago", label: "Filed", sortable: false, format: (_v, r) => <span className={dim}>{relTime(r.filing_date)}</span> },
    ],
    cellOverrides: {
      // Raw "2026Q1" -> "Q1 2026", coloured by how long ago it was filed (freshness).
      quarter: (v, r) => <span className={freshnessClass(daysAgo(r.filing_date))}>{quarterLabel(v)}</span>,
    },
  },
  "macro": { table: "macro_indicators", title: "Macro Indicators" },
  "mf-holdings": {
    table: "mf_stock_holdings",
    title: "MF Stock Holdings",
    banner: <Banner tone="info">AMFI portfolio data is published by the 10th of the following month.</Banner>,
    cellOverrides: {
      month: (v) => <span className="text-slate-200">{monthLabel(v)}</span>,
    },
  },
  "news": { table: "news_sentiment", title: "News Sentiment" },
  "pledging": { table: "pledging_alerts", title: "Pledging Alerts" },
  "quarterly-financials": { table: "quarterly_financials", title: "Quarterly Financials" },
  "quotes": { table: "quotes", title: "Live Quotes" },
  "recompute-queue": { table: "recompute_queue", title: "Recompute Queue" },
  "sast": {
    table: "sast_disclosures",
    title: "SAST Disclosures",
    banner: <Banner>⚠️ SEBI SAST rules require disclosure within <b>2 working days</b> of acquisition. Rows exceeding that (where an acquisition date is available) are flagged red.</Banner>,
    extraColumns: [
      {
        key: "_days_to_disclose", label: "Days to Disclose", sortable: false,
        format: (_v, r) => {
          const d = diffDays(r.disclosure_date, r.acquisition_date);
          if (d == null) return <span className={dim}>—</span>;
          return <span className={d > 2 ? "text-sell font-medium" : "text-slate-300"}>{d}d{d > 2 ? " ⚠" : ""}</span>;
        },
      },
    ],
  },
  "shareholding": {
    table: "shareholding_pattern",
    title: "Shareholding Pattern",
    banner: <Banner tone="info">Shareholding is filed quarterly with SEBI — data may be up to ~3 months old.</Banner>,
    cellOverrides: {
      quarter_end: (v) => <span className="text-slate-200">{fyQuarterLabel(v)}</span>,
    },
  },
  "stock-scores": { table: "stock_scores", title: "Stock Scores" },
  "stocks": { table: "stocks", title: "Stock Universe" },
  "technicals": { table: "technical_indicators", title: "Technical Indicators" },
  "tracked-filers": { table: "tracked_filers", title: "Tracked 13F Filers" },
  "watchlist": { table: "watchlist", title: "Watchlist" },
  "watchlist-changes": { table: "watchlist_changes", title: "Watchlist Changes" },
  "whatsapp": { table: "whatsapp_messages", title: "WhatsApp Messages" },
};

export default function RawData() {
  const { slug } = useParams<{ slug: string }>();

  if (!slug || !TABLE_CONFIG[slug]) {
    return (
      <div className="text-center py-12 text-slate-400">
        <h1 className="text-xl font-semibold mb-2">Table Not Found</h1>
        <p>The requested data table does not exist.</p>
      </div>
    );
  }

  const config = TABLE_CONFIG[slug];

  return (
    <DataTable
      key={slug}
      table={config.table}
      title={config.title}
      banner={config.banner}
      extraColumns={config.extraColumns}
      cellOverrides={config.cellOverrides}
    />
  );
}
