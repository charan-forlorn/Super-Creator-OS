import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { renameSync, existsSync } from "node:fs";
import { resolve } from "node:path";

// Inject the real absolute path of the E2E sample at build time by replacing a
// sentinel token in the E2E entry. Vite `define` proved unreliable for bare
// identifiers here, so we use an explicit transform. The seed then sets the
// project asset's sourcePath to a genuine filesystem path so the app's Tauri
// asset-protocol resolver (convertFileSrc) can serve it for real playback
// inside the bundled webview.
const E2E_SAMPLE_ABS = resolve(__dirname, "e2e/fixtures/sample.mp4");
const E2E_PROJECT_FIXTURE = process.env.HAIOS_E2E_PROJECT_FIXTURE ?? "default";

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
      name: "haios-e2e-inject-sample-path",
      enforce: "pre",
      transform(code, id) {
        if (id.endsWith("e2e-entry.tsx")) {
          let transformed = code.replace(/__E2E_SAMPLE_ABS_PATH__/g, JSON.stringify(E2E_SAMPLE_ABS));
          if (E2E_PROJECT_FIXTURE === "p43") {
            transformed = transformed.replace("../e2e/fixtures/project.json", "../e2e/fixtures/project-p43.json");
          }
          return transformed;
        }
        return null;
      },
    },
    {
      name: "haios-e2e-tauri-index",
      closeBundle() {
        // Vite emits the E2E entry as `index.e2e.html` (mirrors the source file
        // name); Tauri always loads `index.html`, so rename it.
        const out = resolve("dist-e2e/index.e2e.html");
        const target = resolve("dist-e2e/index.html");
        if (existsSync(out)) renameSync(out, target);
      },
    },
  ],
  clearScreen: false,
  root: ".",
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
