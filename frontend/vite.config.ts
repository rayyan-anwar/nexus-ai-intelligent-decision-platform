import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API runs on :8000 in development; no CORS configuration is needed through this proxy.
    proxy: { "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: true } },
  },
  build: { sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.spec.tsx"],
    setupFiles: ["src/tests/setup.ts"],
  },
});
