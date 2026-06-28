import { useEffect, useState } from "react";
import { api, completenessClass } from "../api";

// Global data-health indicator shown in the header on every page.
export default function DataHealth() {
  const [h, setH] = useState<any>(null);
  useEffect(() => {
    api.qualityHealth().then(setH).catch(() => setH(null));
  }, []);
  if (!h || h.avg_completeness == null) return null;
  const dot = h.avg_completeness >= 90 ? "bg-buy" : h.avg_completeness >= 70 ? "bg-watch" : "bg-sell";
  return (
    <div
      className="flex items-center gap-1.5 text-xs text-slate-400 whitespace-nowrap"
      title={`${h.green} green / ${h.yellow} yellow / ${h.red} red · ${h.open_gaps} open gaps`}
    >
      <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
      Data health <span className={completenessClass(h.avg_completeness)}>{h.avg_completeness}%</span>
      {h.open_gaps > 0 && <span className="text-slate-500">· {h.open_gaps} gaps</span>}
    </div>
  );
}
