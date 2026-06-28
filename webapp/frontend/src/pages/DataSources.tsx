import { useCallback, useEffect, useState } from "react";
import { api, relTime, statusClass } from "../api";
import RefreshButton from "../components/RefreshButton";
import { Loading, Error } from "./Dashboard";

export default function DataSources() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string>();
  const [bulk, setBulk] = useState<{ kind: string; msg: string } | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(() => {
    api.refreshSources().then(setD).catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => load(), [load]);

  async function bulkRefresh(kind: "all" | "failed") {
    setBulkBusy(true);
    setBulk(null);
    try {
      const res = kind === "all" ? await api.triggerAll() : await api.triggerFailed();
      setBulk({ kind, msg: `Launched ${res.ok}/${res.count} ${kind === "failed" ? "failed/never-run " : ""}source${res.count === 1 ? "" : "s"}.` });
      setTimeout(load, 1500);
    } catch (e) {
      setBulk({ kind, msg: `Failed: ${e}` });
    } finally {
      setBulkBusy(false);
    }
  }

  if (err) return <Error msg={err} />;
  if (!d) return <Loading />;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Data Sources</h1>
          <p className="text-sm text-slate-400">
            Every collector, what it provides, and when it last refreshed. From <code className="text-slate-500">data_refresh_log</code>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => bulkRefresh("all")} disabled={bulkBusy || !d.dagster_healthy}
            className="inline-flex items-center gap-1.5 text-xs font-medium border border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10 rounded-md px-3 py-1 disabled:opacity-40">
            {bulkBusy && <span className="inline-block w-3 h-3 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin" />}
            Refresh All
          </button>
          <button onClick={() => bulkRefresh("failed")} disabled={bulkBusy || !d.dagster_healthy}
            className="text-xs font-medium border border-edge text-slate-300 hover:bg-edge/60 rounded-md px-3 py-1 disabled:opacity-40">
            Refresh All Failed
          </button>
          <button onClick={load} className="text-xs text-slate-400 hover:text-slate-200 border border-edge rounded-md px-2.5 py-1">↻ Reload</button>
        </div>
      </div>
      {bulk && <div className="text-xs text-slate-400">{bulk.msg}</div>}

      {!d.dagster_healthy && (
        <div className="card p-3 text-sm text-watch border-watch/30">
          ⚠️ Dagster (localhost:3000) is unreachable — “Refresh Now” is disabled until it’s up.
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[820px]">
          <thead>
            <tr>
              <th className="th">Source</th>
              <th className="th">Provides</th>
              <th className="th">Frequency</th>
              <th className="th">Last refresh</th>
              <th className="th text-right">Rows</th>
              <th className="th">Status</th>
              <th className="th text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {d.sources.map((s: any) => (
              <tr key={s.source} className="hover:bg-edge/30">
                <td className="td font-medium text-slate-100">{s.source}</td>
                <td className="td text-slate-300">{s.provides}</td>
                <td className="td"><span className="text-xs bg-edge/60 rounded px-1.5 py-0.5">{s.frequency}</span></td>
                <td className="td">
                  <span title={s.completed_at || ""}>{relTime(s.completed_at)}</span>
                  {s.stale && <span className="ml-2 text-[10px] text-watch">STALE</span>}
                </td>
                <td className="td text-right">{s.rows_upserted ?? 0}</td>
                <td className="td">
                  <span className={`inline-block px-2 py-0.5 rounded-md border text-xs font-semibold ${statusClass[s.status] || statusClass.never_run}`}>
                    {s.status}
                  </span>
                </td>
                <td className="td text-right">
                  <RefreshButton
                    source={s.source}
                    triggerable={s.triggerable}
                    disabled={!d.dagster_healthy}
                    onDone={load}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-slate-500 flex gap-4">
        <span><span className="inline-block w-2 h-2 rounded-full bg-buy mr-1" />success</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-sell mr-1" />failed</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-slate-500 mr-1" />never run</span>
      </div>
    </div>
  );
}
