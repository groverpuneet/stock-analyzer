import { useCallback, useEffect, useState } from "react";
import { api, relTime, statusClass } from "../api";
import RefreshButton from "../components/RefreshButton";
import { Loading, Error } from "./Dashboard";

export default function RefreshStatus() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();

  const load = useCallback(() => {
    api.refreshStatus().then(setD).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => load(), [load]);

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  const triggerableHint = "Triggerable sources can be refreshed; others have no Dagster asset.";

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Refresh Status</h1>
          <p className="text-sm text-slate-400">Failures, stale sources, and the latest run for each collector.</p>
        </div>
        <button onClick={load} className="text-xs text-slate-400 hover:text-slate-200 border border-edge rounded-md px-2.5 py-1">↻ Reload</button>
      </div>

      {!d.dagster_healthy && (
        <div className="card p-3 text-sm text-watch border-watch/30">
          ⚠️ Dagster (localhost:3000) is unreachable — “Refresh Now” is disabled until it’s up.
        </div>
      )}

      {/* Failures */}
      <Section title="Failed refreshes (last 7 days)" count={d.failures.length}>
        {d.failures.length === 0 ? (
          <Ok msg="No failed refreshes in the last 7 days." />
        ) : (
          <div className="space-y-2">
            {d.failures.map((f: any, i: number) => (
              <div key={i} className="card p-3 border-sell/30 flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-sell">{f.source} <span className="text-xs text-slate-500">({f.tier})</span></div>
                  <div className="text-xs text-slate-400 mt-1">{f.error_message || "no error message"}</div>
                  <div className="text-[11px] text-slate-500">{relTime(f.completed_at)}</div>
                </div>
                <RefreshButton source={f.source} triggerable disabled={!d.dagster_healthy} onDone={load} />
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Stale */}
      <Section title="Stale sources (overdue vs frequency)" count={d.stale.length}>
        {d.stale.length === 0 ? (
          <Ok msg="Every source is within its expected refresh window." />
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead><tr>
                <th className="th">Source</th><th className="th">Frequency</th><th className="th">Last run</th>
                <th className="th">SLA</th><th className="th text-right">Action</th>
              </tr></thead>
              <tbody>
                {d.stale.map((s: any) => (
                  <tr key={s.source} className="hover:bg-edge/30">
                    <td className="td font-medium text-watch">{s.source}</td>
                    <td className="td">{s.tier}</td>
                    <td className="td">{relTime(s.completed_at)}</td>
                    <td className="td text-slate-400">{s.max_age_days ? `≤ ${s.max_age_days}d` : "—"}</td>
                    <td className="td text-right">
                      <RefreshButton source={s.source} triggerable disabled={!d.dagster_healthy} onDone={load} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* History */}
      <Section title="Refresh log — latest run per source" count={d.history.length}>
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[820px]">
            <thead><tr>
              <th className="th">Source</th><th className="th">Status</th><th className="th">Started</th>
              <th className="th">Completed</th><th className="th text-right">Rows</th><th className="th">Error</th>
            </tr></thead>
            <tbody>
              {d.history.map((h: any, i: number) => (
                <tr key={i} className="hover:bg-edge/30">
                  <td className="td font-medium text-slate-100">{h.source}</td>
                  <td className="td">
                    <span className={`inline-block px-2 py-0.5 rounded-md border text-xs font-semibold ${statusClass[h.status] || statusClass.never_run}`}>{h.status}</span>
                  </td>
                  <td className="td text-slate-400" title={h.started_at || ""}>{relTime(h.started_at)}</td>
                  <td className="td text-slate-400" title={h.completed_at || ""}>{relTime(h.completed_at)}</td>
                  <td className="td text-right">{h.rows_upserted ?? 0}</td>
                  <td className="td text-[11px] text-sell max-w-[220px] truncate" title={h.error_message || ""}>{h.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11px] text-slate-500 mt-2">{triggerableHint} data_refresh_log stores one row per source (its most recent run).</p>
      </Section>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-300">
        {title} <span className="text-slate-500">({count})</span>
      </h2>
      {children}
    </div>
  );
}
function Ok({ msg }: { msg: string }) {
  return <div className="card p-3 text-sm text-buy border-buy/20">✓ {msg}</div>;
}
