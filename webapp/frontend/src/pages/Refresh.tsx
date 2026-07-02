import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, relTime, statusClass } from "../api";
import { Loading, Error } from "./Dashboard";

// Single unified refresh control page. Reads the truth from data_refresh_log
// (/api/refresh/control) but tracks IN-FLIGHT manual runs by their Dagster run_id,
// polling /api/dagster/run-status every 3s so every button gives real-time feedback
// (QUEUED → STARTED → SUCCESS/FAILURE) independent of the lagging refresh log.

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
const TERMINAL = new Set(["SUCCESS", "FAILURE", "CANCELED"]);
type RunInfo = { runId: string; state: string; endedAt?: number };
type Toast = { id: number; kind: "ok" | "error" | "info"; msg: string };
type ActionKind = "all" | "failed" | "India" | "US" | "audit";
const ACTION_LABEL: Record<ActionKind, string> = {
  all: "Run All", failed: "Retry Failed", India: "Refresh All India",
  US: "Refresh All US", audit: "Audit",
};

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

function nowClock(): string {
  const d = new Date();
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// Runs that this page launched map to a friendly run-state label + colour.
function runPill(state: string): { label: string; cls: string } {
  if (state === "SUCCESS") return { label: "SUCCESS", cls: statusClass.success };
  if (state === "FAILURE" || state === "CANCELED") return { label: state, cls: statusClass.error };
  if (state === "STARTED" || state === "STARTING") return { label: "STARTED", cls: statusClass.running };
  return { label: "QUEUED", cls: statusClass.running };
}

function StatusIcon({ status, spinning }: { status: string; spinning: boolean }) {
  if (spinning)
    return <span className="inline-block w-3.5 h-3.5 border-2 border-watch border-t-transparent rounded-full animate-spin" />;
  const map: Record<string, string> = {
    success: "✅", error: "❌", stalled: "❌", partial: "⚠️",
    retrying: "🔁", pending: "⏳", never_run: "○",
    SUCCESS: "✅", FAILURE: "❌", CANCELED: "❌",
  };
  const cls =
    status === "success" || status === "SUCCESS" ? "text-buy" :
    status === "error" || status === "stalled" || status === "FAILURE" || status === "CANCELED" ? "text-sell" :
    status === "partial" || status === "retrying" ? "text-watch" : "text-slate-500";
  return <span className={`text-sm ${cls}`}>{map[status] || "○"}</span>;
}

export default function Refresh() {
  const [d, setD] = useState<Control | null>(null);
  const [err, setErr] = useState<string>();
  const [runs, setRuns] = useState<Record<string, RunInfo>>({});
  const [busyAction, setBusyAction] = useState<ActionKind | null>(null);
  const [lastAction, setLastAction] = useState<string>("");
  const [toasts, setToasts] = useState<Toast[]>([]);

  const runsRef = useRef(runs); runsRef.current = runs;
  const busyRef = useRef(busyAction); busyRef.current = busyAction;
  const dRef = useRef(d); dRef.current = d;
  const toastId = useRef(0);

  const load = useCallback(async () => {
    try { setD(await api.refreshControl()); }
    catch (e) { setErr(String(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // source/asset -> label, for toasts + progress text (stable — reads dRef)
  const labelFor = useCallback((src: string) => {
    for (const g of dRef.current?.groups || []) for (const j of g.jobs) if (j.source === src) return j.label;
    if (src === "nse_daily_audit") return "Daily audit";
    if (src === "nse_weekly_audit") return "Weekly audit";
    return src;
  }, []);

  const toast = useCallback((kind: Toast["kind"], msg: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, kind, msg }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  // After an audit run finishes, surface open data-quality gaps inline.
  const [auditResult, setAuditResult] = useState<{ gaps: number; byTable: any[] } | null>(null);
  const reportGaps = useCallback(async () => {
    try {
      const g = await api.qualityGaps();
      const byTable = g.by_table || [];
      const gaps = byTable.reduce((n: number, r: any) => n + Number(r.n || 0), 0);
      setAuditResult({ gaps, byTable });
      toast(gaps ? "info" : "ok", gaps ? `🔍 Audit: ${gaps} open gap${gaps === 1 ? "" : "s"} found` : "🔍 Audit: no open gaps 🎉");
    } catch (e) { toast("error", `Audit ran, but gap fetch failed: ${e}`); }
  }, [toast]);

  // ---- background control refresh: keep rows/duration fresh while anything runs ----
  useEffect(() => {
    const t = window.setInterval(() => {
      const runActive = Object.values(runsRef.current).some((r) => !TERMINAL.has(r.state));
      const dbActive = (d?.groups || []).some((g) => g.jobs.some((j) => RUNNING_STATES.has(j.status)));
      if (runActive || dbActive) load();
    }, 5000);
    return () => window.clearInterval(t);
  }, [d, load]);

  // ---- poll Dagster run-status every 3s for every in-flight run we launched ----
  useEffect(() => {
    const t = window.setInterval(async () => {
      const active = Object.entries(runsRef.current).filter(([, r]) => !TERMINAL.has(r.state));
      if (!active.length) return;
      const updates = await Promise.all(active.map(async ([src, r]) => {
        const st = await api.dagsterRunStatus(r.runId).catch(() => null);
        return { src, status: (st && st.ok !== false ? st.status : "FAILURE") as string | null };
      }));
      const finished: { src: string; status: string }[] = [];
      setRuns((prev) => {
        const next = { ...prev };
        for (const { src, status } of updates) {
          if (!status || !next[src] || TERMINAL.has(next[src].state)) continue;
          next[src] = { ...next[src], state: status };
          if (TERMINAL.has(status)) { next[src].endedAt = Date.now(); finished.push({ src, status }); }
        }
        return next;
      });
      if (finished.length) {
        for (const f of finished) {
          if (f.status === "SUCCESS") toast("ok", `✅ ${labelFor(f.src)} completed`);
          else toast("error", `❌ ${labelFor(f.src)} ${f.status.toLowerCase()}`);
          // drop the overlay after 8s so the row reverts to the (now updated) DB truth
          const src = f.src;
          window.setTimeout(() => setRuns((p) => {
            const n = { ...p }; if (n[src] && TERMINAL.has(n[src].state)) delete n[src]; return n;
          }), 8000);
        }
        load(); // refresh rows/duration from data_refresh_log
      }
      // if the current bulk action's runs are all terminal, mark it done
      if (busyRef.current) {
        const anyActive = Object.values(runsRef.current).some((r) => !TERMINAL.has(r.state));
        if (!anyActive) {
          const kind = busyRef.current;
          const done = Object.values(runsRef.current).filter((r) => r.state === "SUCCESS").length;
          const totalNow = Object.keys(runsRef.current).length;
          toast("ok", `✅ ${ACTION_LABEL[kind]} complete — ${done}/${totalNow} succeeded`);
          setBusyAction(null);
          if (kind === "audit") reportGaps();
        }
      }
    }, 3000);
    return () => window.clearInterval(t);
  }, [labelFor, load, toast, reportGaps]);

  // Ingest a set of just-launched runs into the tracker + fire toasts.
  // Bulk endpoints key on `source`; the audit endpoint keys on `asset`.
  const ingest = useCallback((launched: any[]): number => {
    let okCount = 0;
    setRuns((prev) => {
      const next = { ...prev };
      for (const l of launched) {
        const key = l.source || l.asset;
        if (l.ok && l.run_id && key) next[key] = { runId: l.run_id, state: l.status || "QUEUED" };
      }
      return next;
    });
    for (const l of launched) {
      const key = l.source || l.asset;
      if (l.ok && l.run_id) { okCount++; toast("ok", `🚀 ${labelFor(key)} launched`); }
      else {
        const already = /already|running|in progress/i.test(l.error || "");
        toast(already ? "info" : "error",
          already ? `🔄 ${labelFor(key)} already running`
                  : `❌ ${labelFor(key)}: ${l.error || "failed to launch"}`);
      }
    }
    return okCount;
  }, [labelFor, toast]);

  const runOne = useCallback(async (source: string) => {
    const existing = runsRef.current[source];
    if ((existing && !TERMINAL.has(existing.state)) || RUNNING_STATES.has(
      (d?.groups || []).flatMap((g) => g.jobs).find((j) => j.source === source)?.status || "")) {
      toast("info", `🔄 ${labelFor(source)} already running`);
      return;
    }
    try {
      const res = await api.trigger(source);
      ingest([{ ...res, source }]);
      if (res.ok) setLastAction(`Run ${labelFor(source)} — launched at ${nowClock()}`);
    } catch (e) {
      toast("error", `❌ ${labelFor(source)}: ${e}`);
    }
  }, [d, labelFor, ingest, toast]);

  const bulk = useCallback(async (kind: ActionKind) => {
    setBusyAction(kind);
    try {
      const res = kind === "all" ? await api.triggerAll()
        : kind === "failed" ? await api.triggerFailed()
        : kind === "audit" ? await api.triggerAudit()
        : await api.triggerRegion(kind);
      const launched: any[] = res.launched || [];
      const okCount = ingest(launched);
      setLastAction(`${ACTION_LABEL[kind]} — ${okCount}/${res.count ?? launched.length} launched at ${nowClock()}`);
      if (!launched.length) {
        toast("info", kind === "failed"
          ? "Nothing to retry — no failed/stalled jobs."
          : `${ACTION_LABEL[kind]}: no jobs to run.`);
        setBusyAction(null);
      } else if (okCount === 0) {
        toast("error", `${ACTION_LABEL[kind]}: 0 launched.`);
        setBusyAction(null);
      }
      load();
    } catch (e) {
      toast("error", `❌ ${ACTION_LABEL[kind]} failed: ${e}`);
      setBusyAction(null);
    }
  }, [ingest, load, toast]);

  // progress across all currently-tracked runs
  const progress = useMemo(() => {
    const all = Object.values(runs);
    const total = all.length;
    const done = all.filter((r) => TERMINAL.has(r.state)).length;
    const active = total > 0 && done < total;
    return { total, done, active, pct: total ? Math.round((done / total) * 100) : 0 };
  }, [runs]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const dagsterDown = !d.dagster_healthy;
  const h = d.health;
  const healthLabel = h.level === "healthy" ? "🟢 Healthy" : h.level === "stale" ? "🟡 Stale" : "🔴 Failed";
  const healthCls = h.color === "green" ? "text-buy" : h.color === "yellow" ? "text-watch" : "text-sell";
  const anyBusy = busyAction !== null || progress.active;

  const history = d.groups.flatMap((g) => g.jobs)
    .filter((j) => j.completed_at)
    .sort((a, b) => (b.completed_at! > a.completed_at! ? 1 : -1))
    .slice(0, 10);

  // Buttons that are currently launching (list them under the buttons)
  const launchingSources = Object.entries(runs).filter(([, r]) => !TERMINAL.has(r.state)).map(([s]) => s);

  const btn = (kind: ActionKind, label: string, cls: string) => (
    <button onClick={() => bulk(kind)} disabled={dagsterDown || busyAction !== null}
      className={`inline-flex items-center gap-1.5 text-xs font-medium rounded-md px-3 py-1.5 disabled:opacity-40 ${cls}`}>
      {busyAction === kind
        ? <><span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />{`${label}…`}</>
        : label}
    </button>
  );

  return (
    <div className="space-y-5">
      {/* Toasts */}
      <div className="fixed top-16 right-4 z-50 space-y-2 w-72">
        {toasts.map((t) => (
          <div key={t.id}
            className={`text-xs rounded-md px-3 py-2 shadow-lg border backdrop-blur bg-ink/90 ${
              t.kind === "ok" ? "border-buy/40 text-buy" :
              t.kind === "error" ? "border-sell/40 text-sell" : "border-edge text-slate-200"}`}>
            {t.msg}
          </div>
        ))}
      </div>

      {/* top progress bar */}
      {anyBusy && (
        <div className="fixed top-0 left-0 right-0 h-0.5 bg-transparent z-50">
          <div className="h-full bg-indigo-400 transition-all duration-500"
            style={{ width: `${progress.total ? Math.max(8, progress.pct) : 30}%` }} />
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">🔄 Data Refresh Control</h1>
          <p className="text-sm text-slate-400">
            Every collector, grouped by market and cadence. One source of truth: <code className="text-slate-500">data_refresh_log</code>.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {btn("all", "▶ Run All Now", "border border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10")}
          {btn("failed", "⚠ Retry Failed", "border border-sell/50 text-sell hover:bg-sell/10")}
          {btn("India", "🔄 Refresh All India", "border border-orange-500/50 text-orange-300 hover:bg-orange-500/10")}
          {btn("US", "🔄 Refresh All US", "border border-blue-500/50 text-blue-300 hover:bg-blue-500/10")}
          {btn("audit", "🔍 Audit", "border border-edge text-slate-300 hover:bg-edge/60")}
          <button onClick={load} disabled={busyAction !== null}
            className="text-xs text-slate-400 hover:text-slate-200 border border-edge rounded-md px-2.5 py-1.5 disabled:opacity-40">↻</button>
        </div>
      </div>

      {/* Last action + currently-launching list */}
      {(lastAction || progress.active) && (
        <div className="text-xs text-slate-400 flex flex-wrap items-center gap-x-3 gap-y-1 -mt-2">
          {lastAction && <span>Last action: <span className="text-slate-300">{lastAction}</span></span>}
          {progress.active && (
            <span className="text-indigo-300">
              🔄 {progress.done}/{progress.total} done{launchingSources.length ? ` · running: ${launchingSources.map(labelFor).join(", ")}` : ""}
            </span>
          )}
        </div>
      )}

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
      </div>

      {dagsterDown && (
        <div className="card p-3 text-sm text-watch border-watch/30">
          ⚠️ Dagster (localhost:3000) is unreachable — triggers are disabled until it’s up.
        </div>
      )}

      {/* Audit result (shown after an Audit run completes) */}
      {auditResult && (
        <div className={`card p-3 text-sm ${auditResult.gaps ? "border-watch/30" : "border-buy/30"}`}>
          <div className="flex items-center justify-between">
            <span className="font-medium text-slate-200">
              🔍 Audit result: {auditResult.gaps ? `${auditResult.gaps} open data-quality gap${auditResult.gaps === 1 ? "" : "s"}` : "no open gaps 🎉"}
            </span>
            <button onClick={() => setAuditResult(null)} className="text-xs text-slate-500 hover:text-slate-300">✕</button>
          </div>
          {auditResult.byTable.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {auditResult.byTable.map((r: any) => (
                <span key={r.table_name} className="text-[11px] bg-edge/60 rounded px-2 py-0.5 text-slate-300">
                  {r.table_name}: <span className="text-watch font-medium">{r.n}</span>
                </span>
              ))}
            </div>
          )}
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
                const run = runs[j.source];
                const runActive = !!run && !TERMINAL.has(run.state);
                const spinning = runActive || (!run && RUNNING_STATES.has(j.status));
                // pill: show live run state while we track a manual run, else the DB status
                const pill = run ? runPill(run.state) : { label: j.status, cls: statusClass[j.status] || statusClass.never_run };
                return (
                  <div key={j.source} className="flex items-center gap-2 px-3 py-1.5 hover:bg-edge/20">
                    <StatusIcon status={run ? run.state : j.status} spinning={spinning} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-slate-200 truncate" title={j.provides}>{j.label}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${pill.cls}`}>{pill.label}</span>
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
                      disabled={runActive || dagsterDown || !j.triggerable}
                      title={!j.triggerable ? "No Dagster asset wired for this source" : `Run ${j.label} now`}
                      className="inline-flex items-center gap-1 text-[11px] border border-edge text-slate-300 hover:bg-edge/60 rounded px-2 py-0.5 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap">
                      {runActive
                        ? <><span className="inline-block w-2.5 h-2.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />{run!.state === "QUEUED" ? "Queued…" : "Running…"}</>
                        : "▶ Run"}
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
