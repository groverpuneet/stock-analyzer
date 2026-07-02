import { useMaterialize } from "../hooks/useMaterialize";
import { relTime } from "../api";

// Small "🔄" icon that materializes ONE Dagster asset. Used in dashboard column
// headers and next to the Fear & Greed gauges. Shows a spinner while running and
// a "Last updated" tooltip. stopPropagation so it doesn't trigger header sorting.
export default function AssetRefresh({
  asset,
  lastUpdated,
  onDone,
  label,
}: {
  asset: string;
  lastUpdated?: string | null;
  onDone?: () => void;
  label?: string;
}) {
  const { state, error, run, busy } = useMaterialize(onDone);
  const icon = busy ? "spin" : state === "ok" ? "✓" : state === "error" ? "⚠" : "🔄";
  const title =
    (label ? `Refresh ${label}. ` : "Refresh. ") +
    `Last updated: ${lastUpdated ? relTime(lastUpdated) : "never"}` +
    (error ? ` — ${error}` : "");
  return (
    <button
      onClick={(e) => { e.stopPropagation(); run(asset); }}
      disabled={busy}
      title={title}
      className={`inline-flex items-center justify-center w-4 h-4 align-middle text-[10px] leading-none rounded hover:bg-edge/60 disabled:opacity-60 ${
        state === "ok" ? "text-buy" : state === "error" ? "text-sell" : "text-slate-400 hover:text-slate-200"
      }`}
    >
      {icon === "spin" ? (
        <span className="inline-block w-2.5 h-2.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
      ) : (
        icon
      )}
    </button>
  );
}
