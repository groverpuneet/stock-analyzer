import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface Alert {
  type: "pledging" | "fii_selling" | "negative_news" | "earnings_miss" | "insider_selling" | "below_sma200";
  severity: "high" | "medium" | "low";
  symbol: string;
  stock_id: number;
  message: string;
  value: number | null;
  date: string;
}

const SEVERITY_COLORS = {
  high: "bg-red-500/20 border-red-500/40 text-red-400",
  medium: "bg-orange-500/20 border-orange-500/40 text-orange-400",
  low: "bg-yellow-500/20 border-yellow-500/40 text-yellow-400",
};

const ALERT_ICONS = {
  pledging: "🔒",
  fii_selling: "📉",
  negative_news: "📰",
  earnings_miss: "💔",
  insider_selling: "👤",
  below_sma200: "📊",
};

export default function RiskAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState<string>("all");
  const [filterSeverity, setFilterSeverity] = useState<string>("all");

  useEffect(() => {
    setLoading(true);
    const fetchAlerts = async () => {
      const allAlerts: Alert[] = [];

      // 1. High pledging (> 20% or rising)
      const pledging = await fetch("/api/data/pledging_alerts?per_page=100").then(r => r.json());
      pledging.data.forEach((p: any) => {
        if (p.pledged_pct > 20 || p.change_pct > 2) {
          allAlerts.push({
            type: "pledging",
            severity: p.pledged_pct > 40 ? "high" : p.pledged_pct > 20 ? "medium" : "low",
            symbol: p.symbol,
            stock_id: p.stock_id,
            message: `Promoter pledging at ${p.pledged_pct?.toFixed(1)}%${p.change_pct > 0 ? ` (↑${p.change_pct?.toFixed(1)}% QoQ)` : ""}`,
            value: p.pledged_pct,
            date: p.date,
          });
        }
      });

      // 2. FII selling (negative net flow for 3+ days)
      const fii = await fetch("/api/macro/fii-dii?limit=10").then(r => r.json());
      let sellStreak = 0;
      for (const f of fii) {
        if (f.fii_net < 0) sellStreak++;
        else break;
      }
      if (sellStreak >= 3) {
        const totalSelling = fii.slice(0, sellStreak).reduce((s: number, f: any) => s + f.fii_net, 0);
        allAlerts.push({
          type: "fii_selling",
          severity: sellStreak >= 5 ? "high" : "medium",
          symbol: "MARKET",
          stock_id: 0,
          message: `FII selling streak: ${sellStreak} days, ₹${Math.abs(totalSelling).toFixed(0)}Cr total outflow`,
          value: totalSelling,
          date: fii[0]?.date,
        });
      }

      // 3. Negative news clusters (3+ negative in 7 days)
      const news = await fetch("/api/data/news_sentiment?per_page=500&date_from=" +
        new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split("T")[0]).then(r => r.json());
      const negativeByStock: Record<number, { symbol: string; count: number; avg: number }> = {};
      news.data.forEach((n: any) => {
        if (n.sentiment_score < -0.3 && n.stock_id) {
          if (!negativeByStock[n.stock_id]) {
            negativeByStock[n.stock_id] = { symbol: n.symbol, count: 0, avg: 0 };
          }
          negativeByStock[n.stock_id].count++;
          negativeByStock[n.stock_id].avg += n.sentiment_score;
        }
      });
      Object.entries(negativeByStock).forEach(([id, data]) => {
        if (data.count >= 3) {
          allAlerts.push({
            type: "negative_news",
            severity: data.count >= 5 ? "high" : "medium",
            symbol: data.symbol,
            stock_id: Number(id),
            message: `${data.count} negative news stories in 7 days (avg score: ${(data.avg / data.count).toFixed(2)})`,
            value: data.count,
            date: new Date().toISOString().split("T")[0],
          });
        }
      });

      // 4. Insider selling
      const insider = await fetch("/api/data/insider_trades?per_page=100&search=SELL").then(r => r.json());
      const insiderByStock: Record<number, { symbol: string; count: number; total: number }> = {};
      insider.data.forEach((t: any) => {
        if (t.transaction === "SELL" && t.stock_id) {
          if (!insiderByStock[t.stock_id]) {
            insiderByStock[t.stock_id] = { symbol: t.symbol, count: 0, total: 0 };
          }
          insiderByStock[t.stock_id].count++;
          insiderByStock[t.stock_id].total += (t.quantity || 0) * (t.price || 0);
        }
      });
      Object.entries(insiderByStock).forEach(([id, data]) => {
        if (data.count >= 2 || data.total > 10_000_000) {
          allAlerts.push({
            type: "insider_selling",
            severity: data.count >= 3 || data.total > 50_000_000 ? "high" : "medium",
            symbol: data.symbol,
            stock_id: Number(id),
            message: `${data.count} insider sales (₹${(data.total / 10_000_000).toFixed(1)}Cr total)`,
            value: data.total,
            date: new Date().toISOString().split("T")[0],
          });
        }
      });

      // 5. Below SMA200
      const technicals = await fetch("/api/data/technical_indicators?per_page=200&sort_by=date&sort_dir=desc").then(r => r.json());
      const latestByStock: Record<number, any> = {};
      technicals.data.forEach((t: any) => {
        if (!latestByStock[t.stock_id]) latestByStock[t.stock_id] = t;
      });
      const prices = await fetch("/api/data/daily_prices?per_page=200&sort_by=date&sort_dir=desc").then(r => r.json());
      const priceByStock: Record<number, number> = {};
      prices.data.forEach((p: any) => {
        if (!priceByStock[p.stock_id]) priceByStock[p.stock_id] = p.close;
      });
      Object.entries(latestByStock).forEach(([id, t]) => {
        const price = priceByStock[Number(id)];
        if (t.sma_200 && price && price < t.sma_200) {
          const pctBelow = ((t.sma_200 - price) / t.sma_200) * 100;
          if (pctBelow > 5) {
            allAlerts.push({
              type: "below_sma200",
              severity: pctBelow > 20 ? "high" : pctBelow > 10 ? "medium" : "low",
              symbol: t.symbol,
              stock_id: t.stock_id,
              message: `Trading ${pctBelow.toFixed(1)}% below SMA200`,
              value: pctBelow,
              date: t.date,
            });
          }
        }
      });

      // Sort by severity
      allAlerts.sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 };
        return order[a.severity] - order[b.severity];
      });

      setAlerts(allAlerts);
      setLoading(false);
    };
    fetchAlerts();
  }, []);

  const filtered = alerts.filter(a => {
    if (filterType !== "all" && a.type !== filterType) return false;
    if (filterSeverity !== "all" && a.severity !== filterSeverity) return false;
    return true;
  });

  const formatDate = (d: string) => {
    if (!d) return "—";
    const dt = new Date(d);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${dt.getDate()}-${months[dt.getMonth()]}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Risk Alerts</h1>
          <p className="text-sm text-slate-400">{filtered.length} active alerts</p>
        </div>
        <div className="flex gap-2">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200"
          >
            <option value="all">All Types</option>
            <option value="pledging">Pledging</option>
            <option value="fii_selling">FII Selling</option>
            <option value="negative_news">Negative News</option>
            <option value="insider_selling">Insider Selling</option>
            <option value="below_sma200">Below SMA200</option>
          </select>
          <select
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200"
          >
            <option value="all">All Severity</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
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
              className={`flex items-center gap-4 p-3 rounded-lg border ${SEVERITY_COLORS[alert.severity]}`}
            >
              <span className="text-2xl">{ALERT_ICONS[alert.type]}</span>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  {alert.stock_id > 0 ? (
                    <Link to={`/stock/${alert.stock_id}`} className="font-medium text-slate-100 hover:underline">
                      {alert.symbol}
                    </Link>
                  ) : (
                    <span className="font-medium text-slate-100">{alert.symbol}</span>
                  )}
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    alert.severity === "high" ? "bg-red-500/30" :
                    alert.severity === "medium" ? "bg-orange-500/30" : "bg-yellow-500/30"
                  }`}>
                    {alert.severity.toUpperCase()}
                  </span>
                </div>
                <p className="text-sm text-slate-300 mt-0.5">{alert.message}</p>
              </div>
              <div className="text-xs text-slate-500">{formatDate(alert.date)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
