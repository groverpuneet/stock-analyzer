import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

interface Holding13F {
  filer_name: string;
  symbol: string;
  stock_id: number;
  shares: number;
  value_usd: number;
  change_shares: number;
  change_pct: number;
  period_end: string;
}

interface SASTRow {
  symbol: string;
  stock_id: number;
  acquirer: string;
  transaction_type: string;
  shares_acquired: number;
  total_holding_pct: number;
  date: string;
}

interface DIIRow {
  symbol: string;
  stock_id: number;
  dii_pct: number;
  prev_dii_pct: number;
  change_pct: number;
  quarter_end: string;
}

export default function SmartMoney() {
  const [tab, setTab] = useState<"13f" | "sast" | "dii">("13f");
  const [holdings, setHoldings] = useState<Holding13F[]>([]);
  const [sast, setSast] = useState<SASTRow[]>([]);
  const [dii, setDii] = useState<DIIRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"buy" | "sell" | "all">("all");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch("/api/data/institutional_holdings_13f?per_page=100&sort_by=period_end&sort_dir=desc").then(r => r.json()),
      fetch("/api/data/sast_disclosures?per_page=100&sort_by=date&sort_dir=desc").then(r => r.json()),
      fetch("/api/data/mf_stock_holdings?per_page=100&sort_by=month&sort_dir=desc").then(r => r.json()),
    ]).then(([h, s, d]) => {
      // Process 13F holdings
      const holdingsData: Holding13F[] = h.data.map((r: any) => ({
        filer_name: r.filer_name,
        symbol: r.symbol,
        stock_id: r.stock_id,
        shares: r.shares,
        value_usd: r.value_usd,
        change_shares: r.change_shares || 0,
        change_pct: r.change_shares && r.shares ? (r.change_shares / (r.shares - r.change_shares)) * 100 : 0,
        period_end: r.period_end,
      }));
      setHoldings(holdingsData);

      // Process SAST
      const sastData: SASTRow[] = s.data.map((r: any) => ({
        symbol: r.symbol,
        stock_id: r.stock_id,
        acquirer: r.acquirer_name,
        transaction_type: r.transaction_type,
        shares_acquired: r.shares_acquired,
        total_holding_pct: r.total_holding_pct,
        date: r.date,
      }));
      setSast(sastData);

      // Process DII from mf_stock_holdings (using ownership_pct as DII proxy)
      const diiData: DIIRow[] = d.data
        .filter((r: any) => r.mom_change_pct !== null)
        .map((r: any) => ({
          symbol: r.symbol,
          stock_id: r.stock_id,
          dii_pct: r.ownership_pct,
          prev_dii_pct: r.ownership_pct - (r.mom_change_pct || 0),
          change_pct: r.mom_change_pct || 0,
          quarter_end: r.month,
        }));
      setDii(diiData);
    }).finally(() => setLoading(false));
  }, []);

  const formatNum = (n: number | null, d = 0) => n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: d });
  const formatPct = (n: number | null) => n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
  const formatDate = (d: string) => {
    const dt = new Date(d);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${dt.getDate()}-${months[dt.getMonth()]}-${dt.getFullYear()}`;
  };

  // Filter based on buy/sell
  const filtered13F = holdings.filter(h => {
    if (filter === "buy") return h.change_shares > 0;
    if (filter === "sell") return h.change_shares < 0;
    return true;
  });

  const filteredSAST = sast.filter(s => {
    if (filter === "buy") return s.transaction_type?.toLowerCase().includes("acquisition");
    if (filter === "sell") return s.transaction_type?.toLowerCase().includes("disposal");
    return true;
  });

  const filteredDII = dii.filter(d => {
    if (filter === "buy") return d.change_pct > 0;
    if (filter === "sell") return d.change_pct < 0;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-100">Smart Money</h1>
        <div className="flex gap-2">
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
        {[
          { key: "13f", label: "SEC 13F Holdings (US)" },
          { key: "sast", label: "SAST Disclosures (India)" },
          { key: "dii", label: "DII Accumulation" },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as any)}
            className={`px-4 py-2 text-sm ${tab === t.key ? "text-blue-400 border-b-2 border-blue-400" : "text-slate-400"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : tab === "13f" ? (
        <div className="overflow-x-auto">
          {filtered13F.length === 0 ? (
            <div className="text-center py-12 text-slate-400">No 13F data available</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-edge text-slate-300">
                <tr>
                  <th className="px-3 py-2 text-left">Fund</th>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-right">Shares</th>
                  <th className="px-3 py-2 text-right">Value ($M)</th>
                  <th className="px-3 py-2 text-right">Change</th>
                  <th className="px-3 py-2 text-left">Period</th>
                </tr>
              </thead>
              <tbody>
                {filtered13F.slice(0, 50).map((h, i) => (
                  <tr key={i} className="border-t border-edge hover:bg-edge/50">
                    <td className="px-3 py-2">{h.filer_name}</td>
                    <td className="px-3 py-2">
                      <Link to={`/stock/${h.stock_id}`} className="text-blue-400 hover:underline">{h.symbol}</Link>
                    </td>
                    <td className="px-3 py-2 text-right">{formatNum(h.shares)}</td>
                    <td className="px-3 py-2 text-right">{formatNum(h.value_usd / 1_000_000, 1)}</td>
                    <td className={`px-3 py-2 text-right ${h.change_shares > 0 ? "text-buy" : h.change_shares < 0 ? "text-sell" : ""}`}>
                      {formatPct(h.change_pct)}
                    </td>
                    <td className="px-3 py-2 text-slate-400">{formatDate(h.period_end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : tab === "sast" ? (
        <div className="overflow-x-auto">
          {filteredSAST.length === 0 ? (
            <div className="text-center py-12 text-slate-400">No SAST disclosures available</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-edge text-slate-300">
                <tr>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-left">Acquirer</th>
                  <th className="px-3 py-2 text-left">Type</th>
                  <th className="px-3 py-2 text-right">Shares</th>
                  <th className="px-3 py-2 text-right">Total %</th>
                  <th className="px-3 py-2 text-left">Date</th>
                </tr>
              </thead>
              <tbody>
                {filteredSAST.slice(0, 50).map((s, i) => (
                  <tr key={i} className="border-t border-edge hover:bg-edge/50">
                    <td className="px-3 py-2">
                      <Link to={`/stock/${s.stock_id}`} className="text-blue-400 hover:underline">{s.symbol}</Link>
                    </td>
                    <td className="px-3 py-2">{s.acquirer}</td>
                    <td className="px-3 py-2">{s.transaction_type}</td>
                    <td className="px-3 py-2 text-right">{formatNum(s.shares_acquired)}</td>
                    <td className="px-3 py-2 text-right">{s.total_holding_pct?.toFixed(2)}%</td>
                    <td className="px-3 py-2 text-slate-400">{formatDate(s.date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          {filteredDII.length === 0 ? (
            <div className="text-center py-12 text-slate-400">No DII accumulation data available</div>
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
                      <Link to={`/stock/${d.stock_id}`} className="text-blue-400 hover:underline">{d.symbol}</Link>
                    </td>
                    <td className="px-3 py-2 text-right">{d.dii_pct?.toFixed(1)}%</td>
                    <td className="px-3 py-2 text-right">{d.prev_dii_pct?.toFixed(1)}%</td>
                    <td className={`px-3 py-2 text-right ${d.change_pct > 0 ? "text-buy" : d.change_pct < 0 ? "text-sell" : ""}`}>
                      {formatPct(d.change_pct)}
                    </td>
                    <td className="px-3 py-2 text-slate-400">{formatDate(d.quarter_end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
