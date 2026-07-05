import { useCallback, useEffect, useState } from "react";
import { api, relTime, statusClass } from "../api";
import { Loading, Error } from "./Dashboard";

// Job Runs page: one row per Dagster run, showing job name, when it kicked off,
// how it was triggered (schedule/sensor/manual), and a derived rollup health.
// Expand a run to see the per-asset SUCCESS/FAILURE breakdown with failure reasons.
//
// The rollup is DERIVED from the per-step events, not Dagster's run-level status
// (which is unreliable on this box — runs finalize as FAILURE even when every
// step succeeded). The raw run status is shown only as a secondary label.

type Asset = { asset: string; status: string; error: string | null };
type Run = {
  run_id: string;
  job: string;
  triggered_by: string;
  kicked_off_at: string | null;
  finished_at: string | null;
  duration_sec: number | null;
  rollup: string; // success | partial | failed | running
  raw_status: string | null;
  assets: Asset[];
};
type RunsResp = { runs: Run[]; dagster_home: string | null };

function fmtDuration(secs: number | null): string {
  if (secs == null) return "—";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60), s = secs % 60;
  if (m < 60) return `${m}m${s ? ` ${s}s` : ""}`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

// map the derived rollup onto the shared statusClass palette
const ROLLUP_STATUS: Record<string, string> = {
  success: "success", failed: "failed", partial: "partial", running: "running",
};

function rollupBadge(rollup: string): { label: string; cls: string } {
  const map: Record<string, string> = {
    success: "✅ SUCCESS", partial: "⚠️ PARTIAL", failed: "❌ FAILED", running: "⏳ RUNNING",
  };
  return {
    label: map[rollup] || rollup,
    cls: statusClass[ROLLUP_STATUS[rollup] || "never_run"] || statusClass.never_run,
  };
}

// green/red dot per asset (mirrors the StatusIcon pattern in Refresh.tsx)
function AssetDot({ status }: { status: string }) {
  const ok = status === "success";
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${ok ? "bg-buy" : "bg-sell"}`}
      title={status}
    />
  );
}

function triggerIcon(t: string): string {
  if (t.startsWith("schedule")) return "🕒";
  if (t.startsWith("sensor")) return "📡";
  return "👤";
}

function RunRow({ run }: { run: Run }) {
  const [open, setOpen] = useState(false);
  const badge = rollupBadge(run.rollup);
  const failedCount = run.assets.filter((a) => a.status === "failed").length;
  const okCount = run.assets.length - failedCount;

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-edge/20 text-left"
      >
        <span className={`text-slate-500 text-xs transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-slate-100 text-sm truncate">{run.job}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls}`}>{badge.label}</span>
            {run.raw_status && run.raw_status !== run.rollup.toUpperCase() && (
              <span className="text-[10px] text-slate-500" title="Raw Dagster run status (unreliable)">
                raw: {run.raw_status}
              </span>
            )}
          </div>
          <div className="text-[11px] text-slate-500 flex gap-2 flex-wrap mt-0.5">
            <span title={run.kicked_off_at || ""}>{relTime(run.kicked_off_at)}</span>
            <span>· {triggerIcon(run.triggered_by)} {run.triggered_by}</span>
            {run.duration_sec != null && <span>· {fmtDuration(run.duration_sec)}</span>}
            {run.assets.length > 0 && (
              <span>· <span className="text-buy">{okCount} ok</span>
                {failedCount > 0 && <span className="text-sell"> · {failedCount} failed</span>}
              </span>
            )}
          </div>
        </div>
      </button>

      {open && (
        <div className="border-t border-edge/60 divide-y divide-edge/40">
          {run.assets.length === 0 ? (
            <div className="px-3 py-2 text-[11px] text-slate-500">
              No per-asset step events recorded for this run.
            </div>
          ) : (
            run.assets.map((a) => (
              <div key={a.asset} className="px-3 py-2 flex items-start gap-2.5">
                <span className="mt-1"><AssetDot status={a.status} /></span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-200">{a.asset}</div>
                  {a.status === "failed" && a.error && (
                    <pre className="mt-1 text-[11px] text-sell whitespace-pre-wrap break-words font-mono bg-sell/5 rounded px-2 py-1 border border-sell/20">
                      {a.error.length > 300 ? a.error.slice(0, 300) + " …" : a.error}
                    </pre>
                  )}
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${
                  a.status === "success" ? statusClass.success : statusClass.failed}`}>
                  {a.status === "success" ? "SUCCESS" : "FAILURE"}
                </span>
              </div>
            ))
          )}
          <div className="px-3 py-1.5 text-[10px] text-slate-600 font-mono">run_id: {run.run_id}</div>
        </div>
      )}
    </div>
  );
}

export default function JobRuns() {
  const [d, setD] = useState<RunsResp | null>(null);
  const [err, setErr] = useState<string>();
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setD(await api.refreshRuns()); setErr(undefined); }
    catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const runs = d.runs;
  const counts = {
    success: runs.filter((r) => r.rollup === "success").length,
    partial: runs.filter((r) => r.rollup === "partial").length,
    failed: runs.filter((r) => r.rollup === "failed").length,
    running: runs.filter((r) => r.rollup === "running").length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">🗂️ Job Runs</h1>
          <p className="text-sm text-slate-400">
            Every Dagster run, most recent first. Health is derived from per-asset steps
            (the run-level status is unreliable). Expand a run to see which asset failed and why.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs text-slate-300 border border-edge rounded-md px-3 py-1.5 hover:bg-edge/60 disabled:opacity-40"
        >
          {loading
            ? <><span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />Refreshing…</>
            : "↻ Refresh"}
        </button>
      </div>

      <div className="card p-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
        <div className="text-slate-400 text-xs">
          <span className="text-buy">{counts.success} success</span> ·{" "}
          <span className="text-watch">{counts.partial} partial</span> ·{" "}
          <span className="text-sell">{counts.failed} failed</span> ·{" "}
          <span className="text-slate-400">{counts.running} running</span>
          <span className="text-slate-600"> · {runs.length} total</span>
        </div>
        {d.dagster_home && (
          <div className="text-[11px] text-slate-600 font-mono truncate" title={d.dagster_home}>
            DAGSTER_HOME: {d.dagster_home}
          </div>
        )}
      </div>

      {runs.length === 0 ? (
        <div className="card p-6 text-center text-sm text-slate-500">
          No runs found in the active Dagster storage.
        </div>
      ) : (
        <div className="space-y-2">
          {runs.map((r) => <RunRow key={r.run_id} run={r} />)}
        </div>
      )}
    </div>
  );
}
