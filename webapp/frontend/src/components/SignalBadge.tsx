import { verdictClass, Verdict } from "../api";

export default function SignalBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-md border text-xs font-semibold ${verdictClass[verdict]}`}
    >
      {verdict}
    </span>
  );
}
