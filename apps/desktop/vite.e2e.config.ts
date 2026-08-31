import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { renameSync } from "node:fs";
import { resolve } from "node:path";

/**
 * TEST-ONLY build config for the GUI E2E harness.
 *
 * Outputs to `dist-e2e/` (NEVER the production `dist/`), and only when the
 * `e2e` mode is selected (`vite build --mode e2e -c vite.e2e.config.ts`).
 * Tauri always loads `index.html`, so the E2E-only output is renamed from
 * `index.e2e.html` to `dist-e2e/index.html` after bundling.
 */
export default defineConfig({
  plugins: [
    react(),
    {
      name: "haios-e2e-tauri-index",
      closeBundle() {
        renameSync(resolve("dist-e2e/index.e2e.html"), resolve("dist-e2e/index.html"));
      },
    },
  ],
  clearScreen: false,
  root: ".",
  // The H.264/AAC file is a deterministic E2E-only asset, not a production
  // media path. Explicit inclusion lets Vite emit a stable hashed URL.
  assetsInclude: ["**/*.mp4"],
  build: {
    outDir: "dist-e2e",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      input: {
        e2e: "index.e2e.html",
      },
    },
  },
  server: {
    port: 1421,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/target/**"] },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
