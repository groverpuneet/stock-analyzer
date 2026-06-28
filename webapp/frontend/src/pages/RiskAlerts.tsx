import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface Alert {
  type: string;
  label: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  market: "india" | "us";
  symbol: string;
  stock_id: number | null;
  message: string;
  dataPoint: string;
  date: string;
}

const SEVERITY_COLORS = {
  CRITICAL: "bg-red-600/20 border-red-600/50 text-red-400",
  HIGH: "bg-red-500/15 border-red-500/40 text-red-400",
  MEDIUM: "bg-orange-500/15 border-orange-500/40 text-orange-400",
  LOW: "bg-yellow-500/15 border-yellow-500/40 text-yellow-400",
};

const SEVERITY_BADGE = {
  CRITICAL: "bg-red-600 text-white",
  HIGH: "bg-red-500/30 text-red-400",
  MEDIUM: "bg-orange-500/30 text-orange-400",
  LOW: "bg-yellow-500/30 text-yellow-400",
};

export default function RiskAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterMarket, setFilterMarket] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");

  useEffect(() => {
    setLoading(true);
    fetchAlerts().then(setAlerts).finally(() => setLoading(false));
  }, []);

  async function fetchAlerts(): Promise<Alert[]> {
    const allAlerts: Alert[] = [];

    try {
      // 1. High pledging from pledging_alerts
      const pledging = await fetch("/api/data/pledging_alerts?per_page=200").then(r => r.json());
      for (const p of pledging.data || []) {
        if (!p.pledged_pct) continue;
        const pledgePct = parseFloat(p.pledged_pct);
        if (pledgePct > 10) {
          allAlerts.push({
            type: "pledging",
            label: "High Pledging",
            severity: pledgePct > 50 ? "CRITICAL" : pledgePct > 30 ? "HIGH" : pledgePct > 20 ? "MEDIUM" : "LOW",
            market: "india",
            symbol: p.symbol || "—",
            stock_id: p.stock_id,
            message: `Promoter pledging at ${pledgePct.toFixed(1)}%`,
            dataPoint: `Pledged: ${pledgePct.toFixed(1)}%`,
            date: p.date || "",
          });
        }
      }

      // 2. Below SMA200 from technical_indicators + daily_prices
      const technicals = await fetch("/api/data/technical_indicators?per_page=300&sort_by=date&sort_dir=desc").then(r => r.json());
      const prices = await fetch("/api/data/daily_prices?per_page=300&sort_by=date&sort_dir=desc").then(r => r.json());

      const latestTech: Record<number, any> = {};
      for (const t of technicals.data || []) {
        if (!latestTech[t.stock_id]) latestTech[t.stock_id] = t;
      }
      const latestPrice: Record<number, any> = {};
      for (const p of prices.data || []) {
        if (!latestPrice[p.stock_id]) latestPrice[p.stock_id] = p;
      }

      for (const [stockId, tech] of Object.entries(latestTech)) {
        const price = latestPrice[Number(stockId)];
        if (tech.sma_200 && price?.close && price.close < tech.sma_200) {
          const pctBelow = ((tech.sma_200 - price.close) / tech.sma_200) * 100;
          if (pctBelow > 5) {
            // Determine market from exchange
            const isUS = price.symbol && ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"].includes(price.symbol);
            allAlerts.push({
              type: "below_sma200",
              label: "Below SMA200",
              severity: pctBelow > 25 ? "HIGH" : pctBelow > 15 ? "MEDIUM" : "LOW",
              market: isUS ? "us" : "india",
              symbol: tech.symbol || price.symbol || "—",
              stock_id: tech.stock_id,
              message: `Trading ${pctBelow.toFixed(1)}% below 200-day moving average`,
              dataPoint: `₹${price.close.toFixed(2)} vs SMA200: ₹${tech.sma_200.toFixed(2)}`,
              date: price.date || "",
            });
          }
        }
      }

      // 3. FII selling streak
      const fiiDii = await fetch("/api/macro/fii-dii?limit=10").then(r => r.json());
      let sellStreak = 0;
      let totalOutflow = 0;
      for (const f of fiiDii || []) {
        if (f.fii_net < 0) {
          sellStreak++;
          totalOutflow += Math.abs(f.fii_net);
        } else break;
      }
      if (sellStreak >= 3) {
        allAlerts.push({
          type: "fii_selling",
          label: "FII Selling Streak",
          severity: sellStreak >= 5 ? "HIGH" : "MEDIUM",
          market: "india",
          symbol: "MARKET",
          stock_id: null,
          message: `FII net selling for ${sellStreak} consecutive days`,
          dataPoint: `Total outflow: ₹${totalOutflow.toFixed(0)}Cr over ${sellStreak} days`,
          date: fiiDii[0]?.date || "",
        });
      }

      // 4. Negative news clusters
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
      const news = await fetch(`/api/data/news_sentiment?per_page=500&date_from=${weekAgo}`).then(r => r.json());
      const negativeByStock: Record<number, { symbol: string; count: number; avgScore: number }> = {};

      for (const n of news.data || []) {
        if (n.sentiment_score && n.sentiment_score < -0.3 && n.stock_id) {
          if (!negativeByStock[n.stock_id]) {
            negativeByStock[n.stock_id] = { symbol: n.symbol, count: 0, avgScore: 0 };
          }
          negativeByStock[n.stock_id].count++;
          negativeByStock[n.stock_id].avgScore += n.sentiment_score;
        }
      }

      for (const [stockId, data] of Object.entries(negativeByStock)) {
        if (data.count >= 3) {
          const avgScore = data.avgScore / data.count;
          allAlerts.push({
            type: "negative_news",
            label: "Negative News Cluster",
            severity: data.count >= 5 ? "HIGH" : "MEDIUM",
            market: "india",
            symbol: data.symbol,
            stock_id: Number(stockId),
            message: `${data.count} negative news stories in last 7 days`,
            dataPoint: `Avg sentiment: ${avgScore.toFixed(2)} (${data.count} stories)`,
            date: new Date().toISOString().split("T")[0],
          });
        }
      }

      // 5. Insider selling clusters
      const insiderClusters = await fetch("/api/smart-money/insider-clusters?days=30").then(r => r.json()).catch(() => ({ clusters: [] }));
      for (const c of insiderClusters.clusters || []) {
        if (c.sell_count >= 2 && c.sell_count > c.buy_count) {
          allAlerts.push({
            type: "insider_selling",
            label: "Insider Selling",
            severity: c.sell_count >= 3 ? "HIGH" : "MEDIUM",
            market: c.exchange === "NYSE" || c.exchange === "NASDAQ" ? "us" : "india",
            symbol: c.symbol,
            stock_id: c.stock_id,
            message: `${c.sell_count} insider sells vs ${c.buy_count} buys in 30 days`,
            dataPoint: `Total value: ₹${(c.total_value / 10_000_000).toFixed(1)}Cr`,
            date: c.latest_date || "",
          });
        }
      }

    } catch (e) {
      console.error("Error fetching alerts:", e);
    }

    // Sort by severity
    const severityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    allAlerts.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

    return allAlerts;
  }

  const formatDate = (d: string) => {
    if (!d) return "—";
    const dt = new Date(d);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${dt.getDate()}-${months[dt.getMonth()]}`;
  };

  const filtered = alerts.filter(a => {
    if (filterMarket !== "all" && a.market !== filterMarket) return false;
    if (filterType !== "all" && a.type !== filterType) return false;
    return true;
  });

  const alertTypes = [...new Set(alerts.map(a => a.type))];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Risk Alerts</h1>
          <p className="text-sm text-slate-400">{filtered.length} active alerts</p>
        </div>
        <div className="flex gap-2">
          <select
            value={filterMarket}
            onChange={(e) => setFilterMarket(e.target.value)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200"
          >
            <option value="all">All Markets</option>
            <option value="india">🇮🇳 India</option>
            <option value="us">🇺🇸 US</option>
          </select>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200"
          >
            <option value="all">All Types</option>
            {alertTypes.map(t => (
              <option key={t} value={t}>{t.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Analyzing risks...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-slate-400">No alerts matching filters</div>
      ) : (
        <div className="space-y-2">
          {filtered.map((alert, i) => (
            <div
              key={i}
              className={`p-4 rounded-lg border ${SEVERITY_COLORS[alert.severity]}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {/* Market badge */}
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700">
                      {alert.market === "india" ? "🇮🇳" : "🇺🇸"}
                    </span>
                    {/* Type label */}
                    <span className="text-xs font-semibold uppercase text-slate-400">{alert.label}</span>
                    {/* Severity badge */}
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${SEVERITY_BADGE[alert.severity]}`}>
                      {alert.severity}
                    </span>
                  </div>
                  {/* Symbol */}
                  <div className="flex items-center gap-2">
                    {alert.stock_id ? (
                      <Link to={`/stock/${alert.stock_id}`} className="text-lg font-semibold text-slate-100 hover:text-blue-400">
                        {alert.symbol}
                      </Link>
                    ) : (
                      <span className="text-lg font-semibold text-slate-100">{alert.symbol}</span>
                    )}
                  </div>
                  {/* Message */}
                  <p className="text-sm text-slate-300 mt-1">{alert.message}</p>
                  {/* Data point */}
                  <p className="text-xs text-slate-400 mt-1 font-mono bg-slate-800/50 inline-block px-2 py-0.5 rounded">
                    {alert.dataPoint}
                  </p>
                </div>
                {/* Date */}
                <div className="text-xs text-slate-500 whitespace-nowrap">
                  {formatDate(alert.date)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
