import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import StockDetail from "./pages/StockDetail";
import Macro from "./pages/Macro";
import Watchlist from "./pages/Watchlist";
import Opportunities from "./pages/Opportunities";
import ChatWidget from "./components/ChatWidget";

const nav = [
  { to: "/", label: "Signals", end: true },
  { to: "/macro", label: "Macro" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/opportunities", label: "Opportunities" },
];

export default function App() {
  const loc = useLocation();
  const m = loc.pathname.match(/^\/stock\/(\d+)/);
  const focusedStock = m ? Number(m[1]) : undefined;

  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-40 bg-ink/90 backdrop-blur border-b border-edge">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
          <div className="font-bold text-slate-100 whitespace-nowrap">📈 Stock Analyzer</div>
          <nav className="flex gap-1 overflow-x-auto">
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
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stock/:id" element={<StockDetail />} />
          <Route path="/macro" element={<Macro />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/opportunities" element={<Opportunities />} />
        </Routes>
      </main>

      <ChatWidget stockId={focusedStock} />
    </div>
  );
}
