import { useEffect, useState } from "react";
import { api, relTime } from "../api";

// "Last updated: 2h ago" badge for a page. `page` maps to its backing sources
// server-side (PAGE_SOURCES); shows the most recent run among them.

export default function LastUpdated({ page }: { page: string }) {
  const [d, setD] = useState<{ completed_at: string | null; status: string } | null>(null);

  useEffect(() => {
    api.lastUpdated(page).then(setD).catch(() => setD(null));
  }, [page]);

  if (!d) return null;
  const ok = d.status === "success";
  return (
    <div className="text-xs text-slate-500 flex items-center gap-1.5" title={d.completed_at || ""}>
      <span className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-buy" : d.status === "running" ? "bg-watch" : "bg-slate-500"}`} />
      Last updated: <span className="text-slate-400">{relTime(d.completed_at)}</span>
    </div>
  );
}
