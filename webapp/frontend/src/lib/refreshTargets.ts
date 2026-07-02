// Which Dagster assets back each page's data — drives the per-page "🔄 Refresh All"
// button. Kept in one place so page components stay declarative.
export const PAGE_ASSETS: Record<string, string[]> = {
  dashboard: [
    "nse_raw_prices", "nse_technical_indicators", "nse_fundamentals",
    "nse_news_sentiment", "nse_fii_dii_flows", "nse_signals",
  ],
  macro: ["nse_macro_indicators", "us_macro", "india_fear_greed", "us_fear_greed"],
  opportunities: ["nse_news_sentiment", "nse_insider_trades", "nse_signals"],
  smartMoney: ["us_13f_holdings", "nse_sast_disclosures", "nse_insider_trades"],
  riskAlerts: ["nse_pledging_alerts", "nse_fii_dii_flows", "nse_signals"],
  watchlist: ["nse_raw_prices", "nse_technical_indicators", "nse_signals"],
  stock: ["nse_raw_prices", "nse_technical_indicators", "nse_fundamentals", "nse_news_sentiment"],
};

// asset key -> data_refresh_log source (for "last updated" lookups)
export const ASSET_SOURCE: Record<string, string> = {
  nse_raw_prices: "kite_ohlcv",
  nse_technical_indicators: "tech_indicators",
  nse_fundamentals: "screener",
  nse_news_sentiment: "news_sentiment",
  nse_fii_dii_flows: "fii_dii",
  nse_fno_data: "fno_data",
  nse_signals: "signals",
  nse_insider_trades: "insider_trades",
  india_fear_greed: "fear_greed",
  us_fear_greed: "fear_greed",
};
