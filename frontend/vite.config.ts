import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy entries that share a path prefix with a frontend route need a bypass:
// browser page navigations (Accept: text/html) get index.html; API fetches
// (Accept: application/json / */*) are forwarded to the backend as normal.
const spaProxy = (target: string) => ({
  target,
  bypass: (req: { headers: Record<string, string | string[] | undefined> }) =>
    req.headers["accept"]?.toString().includes("text/html") ? "/index.html" : null,
});

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: true, // Required for Docker on Windows/macOS to detect file changes
    },
    port: 5173,
    proxy: {
      "/auth": "http://backend:8000",
      "/pharmapi": "http://backend:8000",
      "/prescriptions": "http://backend:8000",
      "/safety-checks": "http://backend:8000",
      "/spc": "http://backend:8000",
      "/alerts": "http://backend:8000",
      "/messages": "http://backend:8000",
      "/notifications": "http://backend:8000",
      "/health": "http://backend:8000",
      "/documentation": spaProxy("http://backend:8000"),
      "/side-effects": spaProxy("http://backend:8000"),
      "/patients": spaProxy("http://backend:8000"),
      "/instructions": spaProxy("http://backend:8000"),
      "/admin": spaProxy("http://backend:8000"),
    },
  },
});
