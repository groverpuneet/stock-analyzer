import { useRef, useState } from "react";
import { api } from "../api";

// "Refresh Now" — POSTs the trigger, then polls the Dagster run to a terminal
// state, showing a spinner throughout. Calls onDone() when finished so the
// parent can reload data_refresh_log.

type Phase = "idle" | "launching" | "running" | "ok" | "error";

export default function RefreshButton({
  source,
  triggerable,
  disabled,
  onDone,
}: {
  source: string;
  triggerable: boolean;
  disabled?: boolean;
  onDone?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [msg, setMsg] = useState<string>("");
  const timer = useRef<number>();

  async function run() {
    setPhase("launching");
    setMsg("");
    const res = await api.trigger(source);
    if (!res.ok) {
      setPhase("error");
      setMsg(res.error || "Failed to launch");
      return;
    }
    setPhase("running");
    const runId = res.run_id as string;
    let polls = 0;
    const poll = async () => {
      polls += 1;
      const st = await api.runStatus(runId);
      const s = st.status;
      if (s === "SUCCESS") {
        setPhase("ok");
        onDone?.();
        setTimeout(() => setPhase("idle"), 4000);
      } else if (s === "FAILURE" || s === "CANCELED" || !st.ok) {
        setPhase("error");
        setMsg(s || st.error || "run failed");
        onDone?.();
      } else if (polls > 90) {
        setPhase("idle"); // give up watching after ~4.5 min; run continues server-side
      } else {
        timer.current = window.setTimeout(poll, 3000);
      }
    };
    timer.current = window.setTimeout(poll, 2000);
  }

  const busy = phase === "launching" || phase === "running";
  const label =
    phase === "running" ? "Running…" :
    phase === "launching" ? "Starting…" :
    phase === "ok" ? "Done ✓" :
    phase === "error" ? "Failed" : "Refresh Now";

  return (
    <button
      onClick={run}
      disabled={busy || disabled || !triggerable}
      title={!triggerable ? "No Dagster asset wired for this source" : msg || ""}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition
        ${phase === "ok" ? "border-buy/40 text-buy" :
          phase === "error" ? "border-sell/40 text-sell" :
          "border-edge text-slate-300 hover:bg-edge/60"}
        disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {busy && (
        <span className="inline-block w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
      )}
      {label}
    </button>
  );
}
