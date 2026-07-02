import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { portfolio, isLocalhost, fmt } from "../api";
import MarketBadge from "../components/MarketBadge";

const SEV: Record<string, string> = {
  CRITICAL: "bg-red-600/20 border-red-600/50 text-red-400",
  HIGH: "bg-orange-500/15 border-orange-500/40 text-orange-400",
  MEDIUM: "bg-yellow-500/15 border-yellow-500/40 text-yellow-400",
  INFO: "bg-blue-500/15 border-blue-500/40 text-blue-300",
};

export default function Portfolio() {
  const [verified, setVerified] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!isLocalhost()) { setChecking(false); return; }
    portfolio.status().then((s) => setVerified(s.verified)).catch(() => setVerified(false)).finally(() => setChecking(false));
  }, []);

  if (!isLocalhost()) {
    return (
      <div className="max-w-lg mx-auto mt-16 card p-6 text-center">
        <div className="text-3xl mb-2">🔒</div>
        <h1 className="text-lg font-semibold text-slate-100 mb-1">Portfolio is localhost-only</h1>
        <p className="text-sm text-slate-400">
          This section is blocked over the tunnel/ngrok and any external network. Open the app
          directly on the host machine (http://localhost:5173) to access your portfolio.
        </p>
      </div>
    );
  }
  if (checking) return <div className="text-slate-400 text-sm py-12 text-center">Checking…</div>;
  if (!verified) return <TotpGate onVerified={() => setVerified(true)} />;
  return <PortfolioDashboard onExpired={() => setVerified(false)} />;
}

// ── TOTP verification screen ──────────────────────────────────────────────────
function TotpGate({ onVerified }: { onVerified: () => void }) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const r = await portfolio.verifyTotp(code.trim());
      if (r.ok) onVerified();
      else setErr(r.status === 401 ? "Invalid code — try the current 6 digits" : `Error (${r.status})`);
    } catch { setErr("Network error"); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-sm mx-auto mt-16 card p-6">
      <div className="text-center mb-4">
        <div className="text-3xl mb-2">🔐</div>
        <h1 className="text-lg font-semibold text-slate-100">Portfolio access</h1>
        <p className="text-xs text-slate-400 mt-1">Enter the 6-digit code from your authenticator app.</p>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <input
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          inputMode="numeric" autoFocus placeholder="000000"
          className="w-full text-center tracking-[0.4em] text-xl bg-ink border border-edge rounded-md px-3 py-2 outline-none focus:border-indigo-500"
        />
        {err && <div className="text-xs text-sell text-center">{err}</div>}
        <button disabled={busy || code.length !== 6}
          className="w-full py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm">
          {busy ? "Verifying…" : "Verify"}
        </button>
      </form>
      <p className="text-[11px] text-slate-500 mt-3 text-center">Access expires 15 min after verification.</p>
    </div>
  );
}

// ── Portfolio dashboard ───────────────────────────────────────────────────────
function PortfolioDashboard({ onExpired }: { onExpired: () => void }) {
  const [holdings, setHoldings] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [remaining, setRemaining] = useState(15 * 60);

  const load = useCallback(() => {
    portfolio.holdings().then((d) => setHoldings(d.holdings)).catch((e) => { if (e.status === 401) onExpired(); });
    portfolio.summary().then(setSummary).catch(() => {});
    portfolio.alerts().then((d) => setAlerts(d.alerts)).catch(() => {});
  }, [onExpired]);

  useEffect(() => { load(); }, [load]);

  // 15-min countdown → force re-verification
  useEffect(() => {
    const t = setInterval(() => setRemaining((r) => {
      if (r <= 1) { clearInterval(t); onExpired(); return 0; }
      return r - 1;
    }), 1000);
    return () => clearInterval(t);
  }, [onExpired]);

  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">💼 Portfolio</h1>
          <p className="text-sm text-slate-400">Private · localhost-only · encrypted at rest. P&amp;L computed live, never stored.</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2 py-1 rounded border ${remaining < 120 ? "border-sell/40 text-sell" : "border-edge text-slate-400"}`}>
            Session {mm}:{ss}
          </span>
          <button onClick={() => portfolio.logout().then(onExpired)} className="text-xs text-slate-400 hover:text-slate-200">Lock</button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Holdings" value={String(summary.holdings_count)} />
          <Stat label="Invested" value={fmt.num(summary.invested, 0)} />
          <Stat label="Current value" value={fmt.num(summary.current_value, 0)} />
          <Stat label="Unrealized P&L" value={`${summary.unrealized_pnl >= 0 ? "+" : ""}${fmt.num(summary.unrealized_pnl, 0)}`}
            cls={summary.unrealized_pnl >= 0 ? "text-buy" : "text-sell"}
            sub={summary.pnl_pct != null ? `${summary.pnl_pct >= 0 ? "+" : ""}${summary.pnl_pct}%` : ""} />
        </div>
      )}

      {alerts.length > 0 && (
        <div className="card p-4">
          <div className="text-sm font-semibold text-slate-300 mb-2">Alerts</div>
          <div className="space-y-2">
            {alerts.map((a, i) => (
              <div key={i} className={`px-3 py-2 rounded border text-sm flex items-center gap-2 ${SEV[a.severity] || "border-edge"}`}>
                <span className="text-xs font-semibold">{a.severity}</span>
                <span>{a.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <UploadPanel onSaved={load} />

      <HoldingsTable holdings={holdings} onChanged={load} />
    </div>
  );
}

function Stat({ label, value, cls, sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className="card p-3">
      <div className="stat-label">{label}</div>
      <div className={`text-lg font-semibold ${cls || "text-slate-100"}`}>{value}</div>
      {sub && <div className={`text-[11px] ${cls || "text-slate-500"}`}>{sub}</div>}
    </div>
  );
}

// ── Upload (drag/drop + preview + confirm) ────────────────────────────────────
function UploadPanel({ onSaved }: { onSaved: () => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [validCount, setValidCount] = useState(0);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setBusy(true); setMsg(""); setRows(null);
    try {
      const r = await portfolio.preview(file);
      if (!r.ok) { const d = await r.json().catch(() => ({})); setMsg(d.detail || `Preview failed (${r.status})`); return; }
      const d = await r.json();
      setRows(d.rows); setValidCount(d.valid_count);
    } catch { setMsg("Upload error"); }
    finally { setBusy(false); }
  }

  async function confirmSave() {
    if (!rows) return;
    setBusy(true); setMsg("");
    const valid = rows.filter((r) => r.valid);
    const r = await portfolio.save(valid, replace);
    if (r.ok) { const d = await r.json(); setMsg(`Saved ${d.saved} holding(s).`); setRows(null); onSaved(); }
    else { const d = await r.json().catch(() => ({})); setMsg(d.detail || `Save failed (${r.status})`); }
    setBusy(false);
  }

  return (
    <div className="card p-4">
      <div className="text-sm font-semibold text-slate-300 mb-2">Upload holdings (CSV / Excel)</div>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); }}
        onClick={() => inputRef.current?.click()}
        className="border border-dashed border-edge rounded-lg py-6 text-center text-sm text-slate-400 cursor-pointer hover:border-indigo-500/50"
      >
        Drag &amp; drop a file here, or click to choose
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
      </div>
      <p className="text-[11px] text-slate-500 mt-2">
        Columns: <code>symbol, exchange, quantity, buying_price, buying_date, target_price, stop_loss, notes</code>
        &nbsp;— e.g. <code>SBIN, NSE, 100, 650.00, 2025-01-15, 800.00, 580.00, Long term hold</code>
      </p>
      {busy && <div className="text-xs text-indigo-300 mt-2">Working…</div>}
      {msg && <div className="text-xs text-slate-300 mt-2">{msg}</div>}

      {rows && (
        <div className="mt-3">
          <div className="text-xs text-slate-400 mb-1">Preview — {validCount}/{rows.length} valid</div>
          <div className="overflow-x-auto max-h-72">
            <table className="w-full text-xs">
              <thead><tr>
                <th className="th">OK</th><th className="th">Symbol</th><th className="th">Exch</th>
                <th className="th text-right">Qty</th><th className="th text-right">Buy</th>
                <th className="th text-right">Target</th><th className="th text-right">Stop</th><th className="th">Issue</th>
              </tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={r.valid ? "" : "bg-sell/5"}>
                    <td className="td">{r.valid ? "✓" : "✕"}</td>
                    <td className="td font-medium">{r.symbol}</td>
                    <td className="td">{r.exchange || "—"}</td>
                    <td className="td text-right">{r.quantity}</td>
                    <td className="td text-right">{r.buying_price}</td>
                    <td className="td text-right">{r.target_price ?? "—"}</td>
                    <td className="td text-right">{r.stop_loss ?? "—"}</td>
                    <td className="td text-sell">{r.error || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3 mt-3">
            <label className="text-xs text-slate-400 flex items-center gap-1">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
              Replace existing holdings
            </label>
            <button disabled={busy || validCount === 0} onClick={confirmSave}
              className="px-4 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm">
              Confirm &amp; save {validCount} holding(s)
            </button>
            <button onClick={() => setRows(null)} className="text-xs text-slate-400 hover:text-slate-200">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function HoldingsTable({ holdings, onChanged }: { holdings: any[]; onChanged: () => void }) {
  async function del(id: number) {
    await portfolio.deleteHolding(id);
    onChanged();
  }
  if (!holdings.length) return <div className="card p-4 text-sm text-slate-500">No holdings yet — upload a file above.</div>;
  const us = (e?: string) => e === "NYSE" || e === "NASDAQ";
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr>
          <th className="th">Symbol</th><th className="th">Market</th>
          <th className="th text-right">Qty</th><th className="th text-right">Buy</th><th className="th text-right">Current</th>
          <th className="th text-right">P&L</th><th className="th text-right">P&L %</th>
          <th className="th text-right">Target</th><th className="th text-right">Stop</th><th className="th"></th>
        </tr></thead>
        <tbody>
          {holdings.map((h) => {
            const cur = (v: number | null) => v == null ? "—" : (us(h.exchange) ? `$${fmt.num(v)}` : fmt.rupee(v));
            return (
              <tr key={h.id} className="hover:bg-edge/30">
                <td className="td"><Link to={`/stock/${h.stock_id || ""}`} className="text-indigo-300">{h.symbol}</Link>
                  {h.notes && <div className="text-[11px] text-slate-500 truncate max-w-[160px]">{h.notes}</div>}</td>
                <td className="td"><MarketBadge exchange={h.exchange} /></td>
                <td className="td text-right">{fmt.num(h.quantity, 0)}</td>
                <td className="td text-right">{cur(h.buying_price)}</td>
                <td className="td text-right">{cur(h.current_price)}</td>
                <td className={`td text-right ${h.unrealized_pnl >= 0 ? "text-buy" : "text-sell"}`}>{h.unrealized_pnl == null ? "—" : `${h.unrealized_pnl >= 0 ? "+" : ""}${fmt.num(h.unrealized_pnl, 0)}`}</td>
                <td className={`td text-right ${h.pnl_pct >= 0 ? "text-buy" : "text-sell"}`}>{h.pnl_pct == null ? "—" : `${h.pnl_pct >= 0 ? "+" : ""}${h.pnl_pct}%`}</td>
                <td className="td text-right">{cur(h.target_price)}</td>
                <td className="td text-right">{cur(h.stop_loss)}</td>
                <td className="td text-right"><button onClick={() => del(h.id)} className="text-xs text-slate-500 hover:text-sell">remove</button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
