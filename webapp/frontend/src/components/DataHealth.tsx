import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

// Global data-health banner in the header on every page. Reads the SAME source
// of truth as the /refresh page (data_refresh_log via /api/refresh/health), so
// no page can disagree about what's healthy. Click -> Refresh control page.
export default function DataHealth() {
  const [h, setH] = useState<any>(null);
  useEffect(() => {
    const load = () => api.refreshHealth().then(setH).catch(() => setH(null));
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  if (!h) return null;
  const dot = h.color === "green" ? "bg-buy" : h.color === "yellow" ? "bg-watch" : "bg-sell";
  const cls = h.color === "green" ? "text-buy" : h.color === "yellow" ? "text-watch" : "text-sell";
  const label = h.level === "healthy" ? "Healthy" : h.level === "stale" ? "Stale" : "Failed";
  const c = h.counts || {};
  return (
    <Link
      to="/refresh"
      className="flex items-center gap-1.5 text-xs text-slate-400 whitespace-nowrap hover:text-slate-200"
      title={`${c.success ?? 0} ok / ${c.failed ?? 0} failed / ${c.attention ?? 0} attention / ${c.stale ?? 0} stale — click for Refresh control`}
    >
      <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
      Data <span className={cls}>{label}</span>
      {c.failed > 0 && <span className="text-sell">· {c.failed} failed</span>}
    </Link>
  );
}
