import { useParams } from "react-router-dom";
import DataTable from "../components/DataTable";

// Map URL slugs to table names and titles
const TABLE_CONFIG: Record<string, { table: string; title: string }> = {
  "analyst-targets": { table: "analyst_targets", title: "Analyst Targets" },
  "bulk-deals": { table: "bulk_deals", title: "Bulk & Block Deals" },
  "concalls": { table: "concall_transcripts", title: "Concall Transcripts" },
  "congress-trades": { table: "congress_trades", title: "Congress Trades" },
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
  "insider-trades": { table: "insider_trades", title: "Insider Trades" },
  "13f": { table: "institutional_holdings_13f", title: "SEC 13F Holdings" },
  "macro": { table: "macro_indicators", title: "Macro Indicators" },
  "mf-holdings": { table: "mf_stock_holdings", title: "MF Stock Holdings" },
  "news": { table: "news_sentiment", title: "News Sentiment" },
  "pledging": { table: "pledging_alerts", title: "Pledging Alerts" },
  "quarterly-financials": { table: "quarterly_financials", title: "Quarterly Financials" },
  "quotes": { table: "quotes", title: "Live Quotes" },
  "recompute-queue": { table: "recompute_queue", title: "Recompute Queue" },
  "sast": { table: "sast_disclosures", title: "SAST Disclosures" },
  "shareholding": { table: "shareholding_pattern", title: "Shareholding Pattern" },
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

  return <DataTable key={slug} table={config.table} title={config.title} />;
}
