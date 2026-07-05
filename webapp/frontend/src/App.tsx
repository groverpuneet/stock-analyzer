import { useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import StockDetail from "./pages/StockDetail";
import Macro from "./pages/Macro";
import Watchlist from "./pages/Watchlist";
import Opportunities from "./pages/Opportunities";
import SmartMoney from "./pages/SmartMoney";
import RiskAlerts from "./pages/RiskAlerts";
import Refresh from "./pages/Refresh";
import JobRuns from "./pages/JobRuns";
import RawDataIndex from "./pages/RawDataIndex";
import RawData from "./pages/RawData";
import Portfolio from "./pages/Portfolio";
import SignalEngine from "./pages/SignalEngine";
import ChatWidget from "./components/ChatWidget";
import DataHealth from "./components/DataHealth";
import { auth, isLocalhost } from "./api";

async function handleLogout() {
  try {
    await auth.logout();
  } finally {
    window.location.reload();
  }
}

const nav = [
  { to: "/", label: "Signals", end: true },
  { to: "/signal-engine", label: "🎯 Signal Engine" },
  { to: "/opportunities", label: "Opportunities" },
  { to: "/smart-money", label: "Smart Money" },
  { to: "/risk-alerts", label: "Risk Alerts" },
  { to: "/macro", label: "Macro" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/refresh", label: "Refresh" },
  { to: "/job-runs", label: "Job Runs" },
  // Portfolio is private + localhost-only: only surface the tab on the host machine.
  ...(isLocalhost() ? [{ to: "/portfolio", label: "💼 Portfolio" }] : []),
];

// Raw Data submenu categories
const rawDataCategories = [
  {
    title: "Market Data",
    items: [
      { to: "/data/prices", label: "Prices" },
      { to: "/data/quotes", label: "Quotes" },
      { to: "/data/technicals", label: "Technicals" },
      { to: "/data/fno", label: "F&O" },
      { to: "/data/expiry-calendar", label: "Expiry Calendar" },
    ],
  },
  {
    title: "Fundamentals",
    items: [
      { to: "/data/fundamentals", label: "Fundamentals" },
      { to: "/data/quarterly-financials", label: "Quarterly" },
      { to: "/data/earnings", label: "Earnings" },
      { to: "/data/concalls", label: "Concalls" },
    ],
  },
  {
    title: "Flows & Activity",
    items: [
      { to: "/data/fii-dii", label: "FII/DII" },
      { to: "/data/insider-trades", label: "Insider" },
      { to: "/data/bulk-deals", label: "Bulk Deals" },
      { to: "/data/sast", label: "SAST" },
      { to: "/data/corporate-actions", label: "Corp Actions" },
    ],
  },
  {
    title: "Sentiment",
    items: [
      { to: "/data/news", label: "News" },
      { to: "/data/whatsapp", label: "WhatsApp" },
    ],
  },
  {
    title: "Institutional",
    items: [
      { to: "/data/13f", label: "13F Holdings" },
      { to: "/data/mf-holdings", label: "MF Holdings" },
      { to: "/data/congress-trades", label: "Congress" },
      { to: "/data/analyst-targets", label: "Analyst" },
      { to: "/data/tracked-filers", label: "Filers" },
    ],
  },
  {
    title: "Risk",
    items: [
      { to: "/data/pledging", label: "Pledging" },
      { to: "/data/shareholding", label: "Shareholding" },
      { to: "/data/stock-scores", label: "Scores" },
      { to: "/data/indicator-baselines", label: "Baselines" },
    ],
  },
  {
    title: "System",
    items: [
      { to: "/data/stocks", label: "Stocks" },
      { to: "/data/watchlist", label: "Watchlist" },
      { to: "/data/watchlist-changes", label: "WL Changes" },
      { to: "/data/macro", label: "Macro" },
      { to: "/data/refresh-log", label: "Refresh Log" },
      { to: "/data/data-quality", label: "Data Quality" },
      { to: "/data/recompute-queue", label: "Recompute Q" },
    ],
  },
];

export default function App() {
  const loc = useLocation();
  const m = loc.pathname.match(/^\/stock\/(\d+)/);
  const focusedStock = m ? Number(m[1]) : undefined;
  const [rawDataOpen, setRawDataOpen] = useState(loc.pathname.startsWith("/data"));

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header className="sticky top-0 z-40 bg-ink/90 backdrop-blur border-b border-edge">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
          <NavLink to="/" className="font-bold text-slate-100 whitespace-nowrap hover:text-white" title="Home — Signals">📈 Stock Analyzer</NavLink>
          <nav className="flex gap-1 overflow-x-auto flex-1 items-center">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm whitespace-nowrap ${
                    isActive ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          {/* Raw Data dropdown - outside nav to avoid overflow clipping */}
          <div className="relative">
              <button
                onClick={() => setRawDataOpen(!rawDataOpen)}
                className={`px-3 py-1.5 rounded-md text-sm whitespace-nowrap flex items-center gap-1 ${
                  loc.pathname.startsWith("/data") ? "bg-edge text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Raw Data
                <svg className={`w-3 h-3 transition-transform ${rawDataOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {rawDataOpen && (
                <div className="absolute right-0 top-full mt-1 w-[90vw] max-w-4xl bg-ink border border-edge rounded-lg shadow-xl z-50 p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-4">
                  {rawDataCategories.map((cat) => (
                    <div key={cat.title}>
                      <div className="text-xs font-semibold text-slate-500 uppercase mb-2">{cat.title}</div>
                      {cat.items.map((item) => (
                        <NavLink
                          key={item.to}
                          to={item.to}
                          onClick={() => setRawDataOpen(false)}
                          className={({ isActive }) =>
                            `block py-1 text-sm ${isActive ? "text-blue-400" : "text-slate-400 hover:text-slate-200"}`
                          }
                        >
                          {item.label}
                        </NavLink>
                      ))}
                    </div>
                  ))}
                  <div className="col-span-full border-t border-edge pt-3 mt-2">
                    <NavLink
                      to="/data"
                      onClick={() => setRawDataOpen(false)}
                      className="text-sm text-blue-400 hover:underline"
                    >
                      View All Tables →
                    </NavLink>
                  </div>
                </div>
              )}
            </div>
          <DataHealth />
          <button
            onClick={handleLogout}
            title="Sign out"
            className="px-2 py-1.5 rounded-md text-sm text-slate-400 hover:text-slate-200 whitespace-nowrap"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 w-full px-4 py-4 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stock/:id" element={<StockDetail />} />
          <Route path="/macro" element={<Macro />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/smart-money" element={<SmartMoney />} />
          <Route path="/risk-alerts" element={<RiskAlerts />} />
          <Route path="/refresh" element={<Refresh />} />
          <Route path="/job-runs" element={<JobRuns />} />
          <Route path="/data-sources" element={<Navigate to="/refresh" replace />} />
          <Route path="/refresh-status" element={<Navigate to="/refresh" replace />} />
          <Route path="/data" element={<RawDataIndex />} />
          <Route path="/data/:slug" element={<RawData />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/signal-engine" element={<SignalEngine />} />
        </Routes>
      </main>

      <ChatWidget stockId={focusedStock} />
    </div>
  );
}
