import { useEffect, useState } from "react";
import { auth, setUnauthorizedHandler } from "../api";
import Login from "./Login";

type State = "loading" | "authed" | "anon";

/**
 * Gates the whole app behind login when the backend has auth enabled.
 * - If WEBAPP_USERNAME is unset (auth_enabled=false), renders children directly.
 * - Otherwise checks the session; shows Login until authenticated.
 * - Registers a global 401 handler so an expired session anywhere returns to Login.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>("loading");

  async function check() {
    try {
      const health = await auth.health();
      if (!health.auth_enabled) {
        setState("authed");
        return;
      }
      const st = await auth.status();
      setState(st.authenticated ? "authed" : "anon");
    } catch {
      // health is public; a failure here means the backend is unreachable.
      // Fall back to the login screen rather than a blank app.
      setState("anon");
    }
  }

  useEffect(() => {
    setUnauthorizedHandler(() => setState("anon"));
    check();
  }, []);

  if (state === "loading") {
    return (
      <div className="h-screen flex items-center justify-center bg-ink text-slate-400 text-sm">
        Loading…
      </div>
    );
  }

  if (state === "anon") {
    return <Login onSuccess={() => setState("authed")} />;
  }

  return <>{children}</>;
}
