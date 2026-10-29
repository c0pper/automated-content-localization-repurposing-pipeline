import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // IPv4 on purpose: Node resolves `localhost` to ::1 first, where another service may own :8000.
      "/api": "http://127.0.0.1:8000",
    },
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/lib/test/vitest.setup.ts"],
    // Locale-aware dates render in the viewer's time zone; pin it for stable expectations.
    env: { TZ: "UTC" },
  },
});