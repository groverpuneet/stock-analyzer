import { useCallback, useEffect, useRef, useState } from "react";
import { api, relTime, statusClass } from "../api";
import { Loading, Error } from "./Dashboard";

// Single unified refresh control page. Everything reads from data_refresh_log
// (via /api/refresh/control) — one source of truth. Individual + bulk triggers
// launch Dagster assets; the page polls every 5s while anything is running.

type Job = {
  source: string;
  label: string;
  provides: string;
  status: string;
  raw_status: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_secs: number | null;
  rows_upserted: number | null;
  error_message: string | null;
  coverage_pct: number | null;
  retry_count: number;
  schedule: string;
  next_run: string | null;
  triggerable: boolean;
};
type Group = {
  id: string; title: string; flag: string; region: string;
  schedule: string; next_run: string | null; jobs: Job[];
};
type Control = {
  groups: Group[];
  health: { level: string; color: string; failed: string[]; attention: string[]; stale: string[];
            counts: Record<string, number> };
  last_full_refresh: string | null;
  dagster_healthy: boolean;
  server_time: string;
};

const RUNNING_STATES = new Set(["running", "retrying"]);

function fmtDuration(secs: number | null): string {
  if (secs == null) return "—";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60), s = secs % 60;
  if (m < 60) return `${m}m${s ? ` ${s}s` : ""}`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function fmtNext(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const mins = Math.round((then - Date.now()) / 60000);
  if (mins < 0) return "due";
  if (mins < 60) return `in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `in ${hrs}h`;
  return `in ${Math.floor(hrs / 24)}d`;
}

function StatusIcon({ status, spinning }: { status: string; spinning: boolean }) {
  if (spinning)
    return <span className="inline-block w-3.5 h-3.5 border-2 border-watch border-t-transparent rounded-full animate-spin" />;
  const map: Record<string, string> = {
    success: "✅", error: "❌", stalled: "❌", partial: "⚠️",
    retrying: "🔁", pending: "⏳", never_run: "○",
  };
  const cls =
    status === "success" ? "text-buy" :
    status === "error" || status === "stalled" ? "text-sell" :
    status === "partial" || status === "retrying" ? "text-watch" : "text-slate-500";
  return <span className={`text-sm ${cls}`}>{map[status] || "○"}</span>;
}

export default function Refresh() {
  const [d, setD] = useState<Control | null>(null);
  const [err, setErr] = useState<string>();
  const [pending, setPending] = useState<Record<string, true>>({});
  const [banner, setBanner] = useState<string>("");
  const pendingRef = useRef(pending);
  pendingRef.current = pending;

  const load = useCallback(async () => {
    try {
      const c = await api.refreshControl();
      setD(c);
      // clear local "launching" flags once a source reaches a terminal state
      setPending((prev) => {
        const next = { ...prev };
        for (const g of c.groups)
          for (const j of g.jobs)
            if (next[j.source] && !RUNNING_STATES.has(j.status) && j.status !== "never_run")
              delete next[j.source];
        return next;
      });
    } catch (e) {
      setErr(String(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Poll every 5s while any job is running (DB) or a launch is pending (local).
  useEffect(() => {
    const active = () =>
      Object.keys(pendingRef.current).length > 0 ||
      (d?.groups || []).some((g) => g.jobs.some((j) => RUNNING_STATES.has(j.status)));
    if (!active()) return;
    const t = setInterval(() => { if (active()) load(); }, 5000);
    return () => clearInterval(t);
  }, [d, load]);

  const runOne = useCallback(async (source: string) => {
    setPending((p) => ({ ...p, [source]: true }));
    setBanner("");
    try {
      const res = await api.trigger(source);
      if (!res.ok) {
        setBanner(`Failed to launch ${source}: ${res.error || "unknown error"}`);
        setPending((p) => { const n = { ...p }; delete n[source]; return n; });
      } else {
        setTimeout(load, 1200);
      }
    } catch (e) {
      setBanner(`Failed to launch ${source}: ${e}`);
      setPending((p) => { const n = { ...p }; delete n[source]; return n; });
    }
  }, [load]);

  const bulk = useCallback(async (kind: "all" | "failed" | "audit") => {
    setBanner("");
    try {
      const res = kind === "all" ? await api.triggerAll()
        : kind === "failed" ? await api.triggerFailed()
        : await api.triggerAudit();
      const launched: any[] = res.launched || [];
      const sources: Record<string, true> = {};
      for (const l of launched) if (l.ok && l.source) sources[l.source] = true;
      setPending((p) => ({ ...p, ...sources }));
      const noun = kind === "audit" ? "audit asset" : kind === "failed" ? "failed/stalled source" : "source";
      setBanner(`Launched ${res.ok}/${res.count} ${noun}${res.count === 1 ? "" : "s"}.`);
      setTimeout(load, 1200);
    } catch (e) {
      setBanner(`Failed: ${e}`);
    }
  }, [load]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const dagsterDown = !d.dagster_healthy;
  const h = d.health;
  const healthLabel = h.level === "healthy" ? "🟢 Healthy" : h.level === "stale" ? "🟡 Stale" : "🔴 Failed";
  const healthCls = h.color === "green" ? "text-buy" : h.color === "yellow" ? "text-watch" : "text-sell";

  // recent run history — latest run per source (data_refresh_log keeps one row/source)
  const allJobs = d.groups.flatMap((g) => g.jobs);
  const history = allJobs
    .filter((j) => j.completed_at)
    .sort((a, b) => (b.completed_at! > a.completed_at! ? 1 : -1))
    .slice(0, 10);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">🔄 Data Refresh Control</h1>
          <p className="text-sm text-slate-400">
            Every collector, grouped by market and cadence. One source of truth: <code className="text-slate-500">data_refresh_log</code>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => bulk("all")} disabled={dagsterDown}
            className="inline-flex items-center gap-1.5 text-xs font-medium border border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10 rounded-md px-3 py-1.5 disabled:opacity-40">
            ▶ Run All Now
          </button>
          <button onClick={() => bulk("failed")} disabled={dagsterDown}
            className="text-xs font-medium border border-sell/50 text-sell hover:bg-sell/10 rounded-md px-3 py-1.5 disabled:opacity-40">
            ⚠ Retry Failed
          </button>
          <button onClick={() => bulk("audit")} disabled={dagsterDown}
            className="text-xs font-medium border border-edge text-slate-300 hover:bg-edge/60 rounded-md px-3 py-1.5 disabled:opacity-40">
            🔍 Audit
          </button>
          <button onClick={load}
            className="text-xs text-slate-400 hover:text-slate-200 border border-edge rounded-md px-2.5 py-1.5">↻</button>
        </div>
      </div>

      {/* Summary bar */}
      <div className="card p-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <div>
          <span className="text-slate-500">Overall health: </span>
          <span className={`font-semibold ${healthCls}`}>{healthLabel}</span>
        </div>
        <div><span className="text-slate-500">Last full refresh: </span>
          <span className="text-slate-200">{d.last_full_refresh ? relTime(d.last_full_refresh) : "—"}</span>
        </div>
        <div className="text-slate-400 text-xs">
          {h.counts.success} ok · {h.counts.failed} failed · {h.counts.attention} need attention · {h.counts.stale} stale
        </div>
        {banner && <div className="text-xs text-slate-300 ml-auto">{banner}</div>}
      </div>

      {dagsterDown && (
        <div className="card p-3 text-sm text-watch border-watch/30">
          ⚠️ Dagster (localhost:3000) is unreachable — triggers are disabled until it’s up.
        </div>
      )}

      {/* Job groups */}
      <div className="grid gap-4 md:grid-cols-2">
        {d.groups.map((g) => (
          <div key={g.id} className="card overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-edge bg-edge/20">
              <div className="font-semibold text-slate-100 text-sm">
                <span className="mr-1.5">{g.flag}</span>{g.title}
              </div>
              <div className="text-[11px] text-slate-500">
                {g.schedule}{g.next_run ? ` · next ${fmtNext(g.next_run)}` : ""}
              </div>
            </div>
            <div className="divide-y divide-edge/50">
              {g.jobs.map((j) => {
                const spinning = !!pending[j.source] || RUNNING_STATES.has(j.status);
                return (
                  <div key={j.source} className="flex items-center gap-2 px-3 py-1.5 hover:bg-edge/20">
                    <StatusIcon status={j.status} spinning={spinning} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-slate-200 truncate" title={j.provides}>{j.label}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${statusClass[j.status] || statusClass.never_run}`}>
                          {j.status}
                        </span>
                        {j.retry_count > 0 && <span className="text-[10px] text-slate-500">↻{j.retry_count}</span>}
                      </div>
                      <div className="text-[11px] text-slate-500 flex gap-2 flex-wrap">
                        <span title={j.completed_at || ""}>{relTime(j.completed_at)}</span>
                        {j.rows_upserted != null && <span>· {j.rows_upserted} rows</span>}
                        {j.duration_secs != null && <span>· {fmtDuration(j.duration_secs)}</span>}
                        {(j.status === "error" || j.status === "stalled") && j.error_message &&
                          <span className="text-sell truncate max-w-[180px]" title={j.error_message}>· {j.error_message}</span>}
                        {j.status === "stalled" && !j.error_message &&
                          <span className="text-sell">· stuck running (orphaned)</span>}
                      </div>
                    </div>
                    <button
                      onClick={() => runOne(j.source)}
                      disabled={spinning || dagsterDown || !j.triggerable}
                      title={!j.triggerable ? "No Dagster asset wired for this source" : `Run ${j.label} now`}
                      className="text-[11px] border border-edge text-slate-300 hover:bg-edge/60 rounded px-2 py-0.5 disabled:opacity-30 disabled:cursor-not-allowed whitespace-nowrap">
                      {spinning ? "…" : "▶ Run"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Recent run history */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-300">Recent runs (latest per source)</h2>
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead><tr>
              <th className="th">Source</th><th className="th">Status</th>
              <th className="th">Completed</th><th className="th text-right">Rows</th>
              <th className="th text-right">Duration</th><th className="th">Error</th>
            </tr></thead>
            <tbody>
              {history.map((h2, i) => (
                <tr key={i} className="hover:bg-edge/30">
                  <td className="td font-medium text-slate-100">{h2.label}</td>
                  <td className="td">
                    <span className={`inline-block px-2 py-0.5 rounded-md border text-xs font-semibold ${statusClass[h2.status] || statusClass.never_run}`}>{h2.status}</span>
                  </td>
                  <td className="td text-slate-400" title={h2.completed_at || ""}>{relTime(h2.completed_at)}</td>
                  <td className="td text-right">{h2.rows_upserted ?? 0}</td>
                  <td className="td text-right text-slate-400">{fmtDuration(h2.duration_secs)}</td>
                  <td className="td text-[11px] text-sell max-w-[220px] truncate" title={h2.error_message || ""}>{h2.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
