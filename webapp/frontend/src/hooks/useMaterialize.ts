import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

// Shared logic for every "🔄 Refresh" button: launch a Dagster materialization,
// then poll /api/dagster/run-status every 3s until a terminal state.

export type MatState = "idle" | "launching" | "running" | "ok" | "error";
const TERMINAL = ["SUCCESS", "FAILURE", "CANCELED"];

// Single-asset refresh (column headers, Fear & Greed gauges).
export function useMaterialize(onDone?: () => void) {
  const [state, setState] = useState<MatState>("idle");
  const [error, setError] = useState("");
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const run = useCallback(async (asset: string) => {
    setState("launching"); setError("");
    let res: any;
    try { res = await api.materialize({ asset }); }
    catch (e) { setState("error"); setError(String(e)); return; }
    if (!res?.ok) { setState("error"); setError(res?.error || "launch failed"); return; }
    setState("running");
    let polls = 0;
    const poll = async () => {
      polls += 1;
      const st = await api.dagsterRunStatus(res.run_id).catch(() => ({ ok: false, status: "" }));
      if (st.status === "SUCCESS") { setState("ok"); onDone?.(); timer.current = window.setTimeout(() => setState("idle"), 3000); }
      else if (st.status === "FAILURE" || st.status === "CANCELED" || st.ok === false) {
        setState("error"); setError(st.status || st.error || "run failed"); onDone?.();
      } else if (polls > 100) { setState("idle"); }
      else { timer.current = window.setTimeout(poll, 3000); }
    };
    timer.current = window.setTimeout(poll, 2000);
  }, [onDone]);

  return { state, error, run, busy: state === "launching" || state === "running" };
}

// Multi-asset refresh ("Refresh All" on each page). Launches all, tracks progress.
export function useMaterializeMany(onDone?: () => void) {
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const run = useCallback(async (assets: string[]) => {
    setState("running"); setProgress({ done: 0, total: assets.length });
    const launched = await Promise.all(
      assets.map((a) => api.materialize({ asset: a }).catch(() => ({ ok: false })))
    );
    const runIds: string[] = launched.filter((r: any) => r.ok && r.run_id).map((r: any) => r.run_id);
    if (!runIds.length) { setState("error"); setProgress({ done: 0, total: assets.length }); return; }
    const pending = new Set(runIds);
    setProgress({ done: 0, total: runIds.length });
    let ticks = 0;
    const poll = async () => {
      ticks += 1;
      await Promise.all([...pending].map(async (rid) => {
        const st = await api.dagsterRunStatus(rid).catch(() => ({ ok: false, status: "" }));
        if (TERMINAL.includes(st.status) || st.ok === false) pending.delete(rid);
      }));
      setProgress({ done: runIds.length - pending.size, total: runIds.length });
      if (!pending.size) { setState("done"); onDone?.(); timer.current = window.setTimeout(() => setState("idle"), 3000); }
      else if (ticks > 160) { setState("idle"); onDone?.(); }
      else { timer.current = window.setTimeout(poll, 3000); }
    };
    timer.current = window.setTimeout(poll, 2500);
  }, [onDone]);

  return { state, progress, run, busy: state === "running" };
}
