import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component tests run under jsdom. Kept separate from vite.config.ts so the dev
// server's proxy config stays untouched by the test runner.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
