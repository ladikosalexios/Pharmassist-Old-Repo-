import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth":           "http://127.0.0.1:8000",
      "/pharmapi":       "http://127.0.0.1:8000",
      "/prescriptions":  "http://127.0.0.1:8000",
      "/safety-checks":  "http://127.0.0.1:8000",
      "/alerts":         "http://127.0.0.1:8000",
      "/health":         "http://127.0.0.1:8000",
    },
  },
});
