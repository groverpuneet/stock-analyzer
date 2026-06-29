import { useState } from "react";
import { auth } from "../api";

/** Login screen shown by AuthGate when the backend requires a session and none exists. */
export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await auth.login(username.trim(), password);
      onSuccess();
    } catch (err: any) {
      setError(err?.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-screen flex items-center justify-center bg-ink px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-ink border border-edge rounded-xl shadow-xl p-6 space-y-4"
      >
        <div className="text-center">
          <div className="text-2xl font-bold text-slate-100">📈 Stock Analyzer</div>
          <div className="text-sm text-slate-400 mt-1">Sign in to continue</div>
        </div>

        <div className="space-y-2">
          <label className="block text-xs font-medium text-slate-400">Username</label>
          <input
            type="text"
            autoCapitalize="none"
            autoCorrect="off"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 rounded-md bg-edge/40 border border-edge text-slate-100 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            required
          />
        </div>

        <div className="space-y-2">
          <label className="block text-xs font-medium text-slate-400">Password</label>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 rounded-md bg-edge/40 border border-edge text-slate-100 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            required
          />
        </div>

        {error && (
          <div className="text-sm text-sell bg-sell/10 border border-sell/30 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || !username || !password}
          className="w-full py-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
