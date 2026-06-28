import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface Holding13F {
  filer_name: string;
  filer_category: string;
  symbol: string;
  issuer_name: string;
  shares_held: number;
  market_value_usd: number;
  pct_of_portfolio: number;
  qoq_change_shares: number;
  qoq_change_pct: number;
  quarter: string;
  filing_date: string;
}

interface SASTRow {
  stock_id: number;
  symbol: string;
  acquirer_name: string;
  acquirer_type: string;
  shares_acquired: number;
  pct_acquired: number;
  total_holding_pct: number;
  acquisition_date: string;
  disclosure_date: string;
  transaction_type: string;
}

interface InsiderTrade {
  stock_id: number;
  symbol: string;
  exchange: string;
  date: string;
  person_name: string;
  person_category: string;
  transaction: string;
  quantity: number;
  price: number;
  source: string;
}

interface DIITrend {
  stock_id: number;
  symbol: string;
  quarter_end: string;
  dii_pct: number;
  prev_dii_pct: number;
  change_pct: number;
}

interface InsiderCluster {
  stock_id: number;
  symbol: string;
  exchange: string;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  total_value: number;
  latest_date: string;
}

export default function SmartMoney() {
  const [market, setMarket] = useState<"us" | "india">("us");
  const [tab, setTab] = useState<string>("13f");
  const [holdings, setHoldings] = useState<Holding13F[]>([]);
  const [sast, setSast] = useState<SASTRow[]>([]);
  const [insiderTrades, setInsiderTrades] = useState<InsiderTrade[]>([]);
  const [diiTrends, setDiiTrends] = useState<DIITrend[]>([]);
  const [insiderClusters, setInsiderClusters] = useState<InsiderCluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"buy" | "sell" | "all">("all");

  // Set default tab when market changes
  useEffect(() => {
    if (market === "us") setTab("13f");
    else setTab("sast");
  }, [market]);

  useEffect(() => {
    setLoading(true);
    const fetches = market === "us"
      ? [
          fetch("/api/smart-money/13f?limit=100").then(r => r.json()),
          fetch("/api/smart-money/insider?limit=100&market=us").then(r => r.json()),
        ]
      : [
          fetch("/api/smart-money/sast?limit=100").then(r => r.json()),
          fetch("/api/smart-money/insider?limit=100&market=india").then(r => r.json()),
          fetch("/api/smart-money/dii-trend?limit=50").then(r => r.json()),
          fetch("/api/smart-money/insider-clusters?days=30").then(r => r.json()),
        ];

    Promise.all(fetches).then((results) => {
      if (market === "us") {
        setHoldings(results[0].holdings || []);
        setInsiderTrades(results[1].trades || []);
      } else {
        setSast(results[0].disclosures || []);
        setInsiderTrades(results[1].trades || []);
        setDiiTrends(results[2].trends || []);
        setInsiderClusters(results[3].clusters || []);
      }
    }).finally(() => setLoading(false));
  }, [market]);

  const formatNum = (n: number | null, d = 0) => n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: d });
  const formatPct = (n: number | null) => n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
  const formatDate = (d: string | null) => {
    if (!d) return "—";
    const dt = new Date(d);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${dt.getDate()}-${months[dt.getMonth()]}-${dt.getFullYear()}`;
  };

  // Filter holdings
  const filtered13F = holdings.filter(h => {
    if (filter === "buy") return (h.qoq_change_shares || 0) > 0;
    if (filter === "sell") return (h.qoq_change_shares || 0) < 0;
    return true;
  });

  const filteredSAST = sast.filter(s => {
    if (filter === "buy") return s.transaction_type?.toLowerCase().includes("acquisition") || s.shares_acquired > 0;
    if (filter === "sell") return s.transaction_type?.toLowerCase().includes("disposal");
    return true;
  });

  const filteredInsider = insiderTrades.filter(t => {
    if (filter === "buy") return t.transaction === "BUY";
    if (filter === "sell") return t.transaction === "SELL";
    return true;
  });

  const filteredDII = diiTrends.filter(d => {
    if (filter === "buy") return d.change_pct > 0;
    if (filter === "sell") return d.change_pct < 0;
    return true;
  });

  const usTabs = [
    { key: "13f", label: "SEC 13F Holdings" },
    { key: "insider", label: "Insider Trades" },
  ];

  const indiaTabs = [
    { key: "sast", label: "SAST Disclosures" },
    { key: "insider", label: "Insider Trades" },
    { key: "dii", label: "DII Trend" },
    { key: "clusters", label: "Insider Clusters" },
  ];

  const tabs = market === "us" ? usTabs : indiaTabs;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-xl font-semibold text-slate-100">Smart Money</h1>
        <div className="flex gap-2">
          {/* Market toggle */}
          <div className="flex rounded overflow-hidden border border-slate-600">
            <button
              onClick={() => setMarket("us")}
              className={`px-3 py-1.5 text-sm ${market === "us" ? "bg-blue-600 text-white" : "bg-edge text-slate-400"}`}
            >
              🇺🇸 US
            </button>
            <button
              onClick={() => setMarket("india")}
              className={`px-3 py-1.5 text-sm ${market === "india" ? "bg-blue-600 text-white" : "bg-edge text-slate-400"}`}
            >
              🇮🇳 India
            </button>
          </div>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
            className="px-3 py-1.5 text-sm rounded bg-edge border border-slate-600 text-slate-200"
          >
            <option value="all">All Activity</option>
            <option value="buy">Buying Only</option>
            <option value="sell">Selling Only</option>
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-edge">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm ${tab === t.key ? "text-blue-400 border-b-2 border-blue-400" : "text-slate-400"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : (
        <div className="overflow-x-auto">
          {/* 13F Holdings (US) */}
          {tab === "13f" && market === "us" && (
            filtered13F.length === 0 ? (
              <div className="text-center py-12 text-slate-400">No 13F data available</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-edge text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-left">Fund</th>
                    <th className="px-3 py-2 text-left">Category</th>
                    <th className="px-3 py-2 text-left">Holding</th>
                    <th className="px-3 py-2 text-right">Shares</th>
                    <th className="px-3 py-2 text-right">Value ($M)</th>
                    <th className="px-3 py-2 text-right">% Portfolio</th>
                    <th className="px-3 py-2 text-right">QoQ Change</th>
                    <th className="px-3 py-2 text-left">Quarter</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered13F.slice(0, 100).map((h, i) => (
                    <tr key={i} className="border-t border-edge hover:bg-edge/50">
                      <td className="px-3 py-2 font-medium">{h.filer_name}</td>
                      <td className="px-3 py-2 text-slate-400">{h.filer_category}</td>
                      <td className="px-3 py-2 text-slate-200" title={h.issuer_name}>
                        {h.symbol || h.issuer_name?.slice(0, 25) || "—"}
                        {h.issuer_name && h.issuer_name.length > 25 && "..."}
                      </td>
                      <td className="px-3 py-2 text-right">{formatNum(h.shares_held)}</td>
                      <td className="px-3 py-2 text-right">{h.market_value_usd ? formatNum(h.market_value_usd / 1_000_000, 1) : "—"}</td>
                      <td className="px-3 py-2 text-right">{h.pct_of_portfolio ? `${h.pct_of_portfolio.toFixed(2)}%` : "—"}</td>
                      <td className={`px-3 py-2 text-right ${(h.qoq_change_pct || 0) > 0 ? "text-buy" : (h.qoq_change_pct || 0) < 0 ? "text-sell" : "text-slate-500"}`}>
                        {h.qoq_change_pct != null ? formatPct(h.qoq_change_pct) : "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{h.quarter}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {/* SAST (India) */}
          {tab === "sast" && market === "india" && (
            filteredSAST.length === 0 ? (
              <div className="text-center py-12 text-slate-400">No SAST disclosures available</div>
            ) : (
              <div>
                <p className="text-xs text-slate-500 mb-2">Note: Detailed share counts pending — SAST data shows disclosure events only</p>
                <table className="w-full text-sm">
                  <thead className="bg-edge text-slate-300">
                    <tr>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Acquirer</th>
                      <th className="px-3 py-2 text-left">Type</th>
                      <th className="px-3 py-2 text-left">Transaction</th>
                      <th className="px-3 py-2 text-left">Disclosure Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSAST.slice(0, 100).map((s, i) => (
                      <tr key={i} className="border-t border-edge hover:bg-edge/50">
                        <td className="px-3 py-2">
                          {s.stock_id ? (
                            <Link to={`/stock/${s.stock_id}`} className="text-blue-400 hover:underline">{s.symbol || "—"}</Link>
                          ) : (s.symbol || "—")}
                        </td>
                        <td className="px-3 py-2">{s.acquirer_name || "—"}</td>
                        <td className="px-3 py-2 text-slate-400">{s.acquirer_type || "—"}</td>
                        <td className="px-3 py-2">
                          <span className={s.transaction_type?.includes("ACQUISITION") ? "text-buy" : s.transaction_type?.includes("DISPOSAL") ? "text-sell" : ""}>
                            {s.transaction_type || "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-400">{formatDate(s.disclosure_date || s.acquisition_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {/* Insider Trades */}
          {tab === "insider" && (
            filteredInsider.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                {market === "india"
                  ? "India insider trades not yet collected — NSE SAST data shown in SAST tab"
                  : "No SEC Form 4 filings available"}
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-edge text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-3 py-2 text-left">Date</th>
                    <th className="px-3 py-2 text-left">Person</th>
                    <th className="px-3 py-2 text-left">Role</th>
                    <th className="px-3 py-2 text-center">Action</th>
                    <th className="px-3 py-2 text-right">Quantity</th>
                    <th className="px-3 py-2 text-right">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredInsider.slice(0, 100).map((t, i) => (
                    <tr key={i} className="border-t border-edge hover:bg-edge/50">
                      <td className="px-3 py-2">
                        {t.stock_id ? (
                          <Link to={`/stock/${t.stock_id}`} className="text-blue-400 hover:underline">{t.symbol || "—"}</Link>
                        ) : (t.symbol || "—")}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{formatDate(t.date)}</td>
                      <td className="px-3 py-2">{t.person_name || "—"}</td>
                      <td className="px-3 py-2 text-slate-400">{t.person_category || "—"}</td>
                      <td className={`px-3 py-2 text-center font-medium ${t.transaction === "BUY" ? "text-buy" : t.transaction === "SELL" ? "text-sell" : "text-slate-400"}`}>
                        {t.transaction || "—"}
                      </td>
                      <td className="px-3 py-2 text-right">{t.quantity ? formatNum(t.quantity) : "—"}</td>
                      <td className="px-3 py-2 text-right">{t.price && t.price > 0 ? `$${formatNum(t.price, 2)}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {/* DII Trend (India) */}
          {tab === "dii" && market === "india" && (
            filteredDII.length === 0 ? (
              <div className="text-center py-12 text-slate-400">No DII trend data available</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-edge text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-3 py-2 text-right">DII %</th>
                    <th className="px-3 py-2 text-right">Prev %</th>
                    <th className="px-3 py-2 text-right">Change</th>
                    <th className="px-3 py-2 text-left">Quarter</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDII.slice(0, 50).map((d, i) => (
                    <tr key={i} className="border-t border-edge hover:bg-edge/50">
                      <td className="px-3 py-2">
                        {d.stock_id ? (
                          <Link to={`/stock/${d.stock_id}`} className="text-blue-400 hover:underline">{d.symbol || "—"}</Link>
                        ) : (d.symbol || "—")}
                      </td>
                      <td className="px-3 py-2 text-right">{d.dii_pct != null ? `${d.dii_pct.toFixed(1)}%` : "—"}</td>
                      <td className="px-3 py-2 text-right">{d.prev_dii_pct != null ? `${d.prev_dii_pct.toFixed(1)}%` : "—"}</td>
                      <td className={`px-3 py-2 text-right font-medium ${d.change_pct > 0 ? "text-buy" : d.change_pct < 0 ? "text-sell" : ""}`}>
                        {d.change_pct != null ? formatPct(d.change_pct) : "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{formatDate(d.quarter_end)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {/* Insider Clusters (India) */}
          {tab === "clusters" && market === "india" && (
            insiderClusters.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                No insider clusters found — India insider trade data not yet collected
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-edge text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-3 py-2 text-center">Trades</th>
                    <th className="px-3 py-2 text-center text-buy">Buys</th>
                    <th className="px-3 py-2 text-center text-sell">Sells</th>
                    <th className="px-3 py-2 text-right">Total Value</th>
                    <th className="px-3 py-2 text-left">Latest</th>
                  </tr>
                </thead>
                <tbody>
                  {insiderClusters.map((c, i) => (
                    <tr key={i} className="border-t border-edge hover:bg-edge/50">
                      <td className="px-3 py-2">
                        {c.stock_id ? (
                          <Link to={`/stock/${c.stock_id}`} className="text-blue-400 hover:underline">{c.symbol || "—"}</Link>
                        ) : (c.symbol || "—")}
                      </td>
                      <td className="px-3 py-2 text-center">{c.trade_count || 0}</td>
                      <td className="px-3 py-2 text-center text-buy">{c.buy_count || 0}</td>
                      <td className="px-3 py-2 text-center text-sell">{c.sell_count || 0}</td>
                      <td className="px-3 py-2 text-right">{c.total_value ? `₹${formatNum(c.total_value / 10_000_000, 1)}Cr` : "—"}</td>
                      <td className="px-3 py-2 text-slate-400">{formatDate(c.latest_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>
      )}
    </div>
  );
}
