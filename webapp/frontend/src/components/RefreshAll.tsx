import { useMaterializeMany } from "../hooks/useMaterialize";

// Global "🔄 Refresh All" button for a page — materializes all of the page's
// backing Dagster assets and shows live progress. Place top-right of each page.
export default function RefreshAll({
  assets,
  onDone,
  label = "Refresh All",
}: {
  assets: string[];
  onDone?: () => void;
  label?: string;
}) {
  const { state, progress, run, busy } = useMaterializeMany(onDone);
  return (
    <button
      onClick={() => run(assets)}
      disabled={busy}
      title={`Refresh this page's data (${assets.length} Dagster assets)`}
      className="inline-flex items-center gap-1.5 text-xs font-medium border border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10 rounded-md px-3 py-1.5 disabled:opacity-50"
    >
      {busy ? (
        <span className="inline-block w-3 h-3 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin" />
      ) : (
        <span>🔄</span>
      )}
      {busy ? `Refreshing ${progress.done}/${progress.total}…` : state === "done" ? "Done ✓" : label}
    </button>
  );
}
