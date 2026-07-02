// Market badge — flag + exchange label, colour-coded India vs US.
// Used anywhere mixed-market rows appear (dashboard, watchlist, raw data…).

export function marketOf(exchange?: string | null): "india" | "us" | "other" {
  if (exchange === "NSE" || exchange === "BSE") return "india";
  if (exchange === "NYSE" || exchange === "NASDAQ") return "us";
  return "other";
}

export function flagOf(exchange?: string | null): string {
  const m = marketOf(exchange);
  return m === "india" ? "🇮🇳" : m === "us" ? "🇺🇸" : "🌐";
}

export default function MarketBadge({ exchange }: { exchange?: string | null }) {
  const m = marketOf(exchange);
  const cls =
    m === "india" ? "bg-orange-500/15 text-orange-300 border-orange-500/30"
    : m === "us" ? "bg-blue-500/15 text-blue-300 border-blue-500/30"
    : "bg-slate-600/15 text-slate-400 border-slate-600/30";
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium whitespace-nowrap ${cls}`}>
      <span>{flagOf(exchange)}</span>
      <span>{exchange || "—"}</span>
    </span>
  );
}
