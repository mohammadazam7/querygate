/// <reference types="vitest/config" />
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  // Pyodide is loaded at run time from public/pyodide, not bundled.
  build: { target: "es2022" },
  test: { environment: "node", testTimeout: 60_000, hookTimeout: 120_000 },
});
