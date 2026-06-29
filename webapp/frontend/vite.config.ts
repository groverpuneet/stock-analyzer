import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev + preview servers proxy /api to the FastAPI backend on :8009 so the frontend
// can use same-origin relative URLs (and SSE streaming works without CORS fuss).
//
// host: true binds all interfaces (IPv4 + IPv6). Required for the ngrok tunnel:
// ngrok forwards to 127.0.0.1:5173, but Vite's default ("localhost") bound IPv6-only
// (::1), so the tunnel got connection-refused. The `preview` block mirrors `server`
// because production access goes through `vite preview` (serving the built dist/).
const proxy = {
  "/api": {
    target: "http://localhost:8009",
    changeOrigin: true,
  },
};

// allowedHosts: Vite 5 rejects requests whose Host header isn't in this list with
// a 403 "Blocked request" page — which is what the ngrok hostname hit. The leading
// dot allows the domain and any ngrok-free subdomain (future-proofs domain rotation).
const allowedHosts = ["avalanche-joining-yin.ngrok-free.dev", ".ngrok-free.dev"];

// headers: send the ngrok bypass header so ngrok's free-tier browser interstitial
// is skipped where it honours a response signal.
const headers = { "ngrok-skip-browser-warning": "true" };

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy,
    allowedHosts,
    headers,
  },
  preview: {
    host: true,
    port: 5173,
    proxy,
    allowedHosts,
    headers,
  },
});
