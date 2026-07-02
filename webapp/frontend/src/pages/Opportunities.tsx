import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt } from "../api";
import { Loading, Error } from "./Dashboard";
import MarketBadge, { marketOf } from "../components/MarketBadge";
import LastUpdated from "../components/LastUpdated";
import RefreshAll from "../components/RefreshAll";
import { PAGE_ASSETS } from "../lib/refreshTargets";

export default function Opportunities() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();
  const [market, setMarket] = useState<"all" | "india" | "us">("all");
  const load = useCallback(() => {
    api.opportunities().then(setD).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const filt = useMemo(() => {
    if (!d) return d;
    const f = (arr: any[]) => market === "all" ? arr : (arr || []).filter((x) => marketOf(x.exchange) === market);
    return {
      sentiment_movers: f(d.sentiment_movers),
      momentum: f(d.momentum),
      recent_deals: f(d.recent_deals),
    };
  }, [d, market]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Opportunity Alerts</h1>
          <p className="text-sm text-slate-400">Signals worth a look that aren’t already on your watchlist.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-md overflow-hidden border border-edge">
            {([["all", "All"], ["india", "🇮🇳 India"], ["us", "🇺🇸 US"]] as const).map(([m, lbl]) => (
              <button key={m} onClick={() => setMarket(m)}
                className={`px-3 py-1 text-xs ${market === m ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"}`}>
                {lbl}
              </button>
            ))}
          </div>
          <LastUpdated page="opportunities" />
          <RefreshAll assets={PAGE_ASSETS.opportunities} onDone={load} />
        </div>
      </div>

      <Card title="Strong news sentiment" subtitle="FinBERT-scored headlines, |score| ≥ 0.5, last 30 days">
        {filt.sentiment_movers.length ? (
          <ul className="divide-y divide-edge/60">
            {filt.sentiment_movers.map((m: any, i: number) => (
              <li key={i} className="py-2 flex gap-3 items-start">
                <Link to={`/stock/${m.stock_id}`} className="font-medium text-indigo-300 hover:text-indigo-200 w-24 shrink-0 flex items-center gap-1">
                  <MarketBadge exchange={m.exchange} />{m.symbol}
                </Link>
                <div className="flex-1">
                  <a href={m.url || "#"} target="_blank" rel="noreferrer" className="text-sm text-slate-200 hover:text-indigo-300">{m.headline}</a>
                  <div className="text-[11px] text-slate-500">{m.source} · {m.date}</div>
                </div>
                <span className={`text-sm font-semibold ${m.sentiment_score >= 0 ? "text-buy" : "text-sell"}`}>
                  {Number(m.sentiment_score).toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        ) : <Empty />}
      </Card>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card title="Momentum leaders" subtitle="Top composite score (monthly model)">
          {filt.momentum.length ? (
            <table className="w-full text-sm">
              <thead><tr><th className="th">Market</th><th className="th">Symbol</th><th className="th text-right">Score</th><th className="th text-right">RSI rank</th><th className="th text-right">MACD rank</th></tr></thead>
              <tbody>
                {filt.momentum.map((m: any, i: number) => (
                  <tr key={i}>
                    <td className="td"><MarketBadge exchange={m.exchange} /></td>
                    <td className="td"><Link to={`/stock/${m.stock_id}`} className="text-indigo-300 hover:text-indigo-200">{m.symbol}</Link></td>
                    <td className="td text-right font-semibold">{fmt.num(Number(m.composite_score), 1)}</td>
                    <td className="td text-right">{fmt.num(Number(m.rsi_rank), 0)}</td>
                    <td className="td text-right">{fmt.num(Number(m.macd_rank), 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty note="All scored stocks are already on the watchlist." />}
        </Card>

        <Card title="Notable bulk & block deals" subtitle="Last 30 days, outside the watchlist">
          {filt.recent_deals.length ? (
            <table className="w-full text-sm">
              <thead><tr><th className="th">Market</th><th className="th">Symbol</th><th className="th">Txn</th><th className="th text-right">Qty</th><th className="th">Date</th></tr></thead>
              <tbody>
                {filt.recent_deals.map((b: any, i: number) => (
                  <tr key={i}>
                    <td className="td"><MarketBadge exchange={b.exchange} /></td>
                    <td className="td"><Link to={`/stock/${b.stock_id}`} className="text-indigo-300 hover:text-indigo-200">{b.symbol}</Link></td>
                    <td className={`td ${b.transaction === "BUY" ? "text-buy" : "text-sell"}`}>{b.transaction}</td>
                    <td className="td text-right">{fmt.num(Number(b.quantity), 0)}</td>
                    <td className="td">{b.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty />}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300">{title}</div>
      {subtitle && <div className="text-[11px] text-slate-500 mb-3">{subtitle}</div>}
      <div className={subtitle ? "" : "mt-3"}>{children}</div>
    </div>
  );
}
function Empty({ note }: { note?: string }) {
  return <div className="text-sm text-slate-500">{note || "No data."}</div>;
}
