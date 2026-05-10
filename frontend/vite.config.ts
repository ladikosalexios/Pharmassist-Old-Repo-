import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
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
      "/documentation": "http://backend:8000",
      "/side-effects": "http://backend:8000",
      "/patients": "http://backend:8000",
      "/instructions": "http://backend:8000",
      "/health": "http://backend:8000",
    },
  },
});
