import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

// Stage 6.7 — local frontend test runner for apps/control-center.
// jsdom + Testing Library. Resolves the same "@/..." alias the Next app uses
// (tsconfig paths: "@/*" -> "./*"). No backend, no network, fully offline.
// globals:true so @testing-library/jest-dom can register matchers at import.
// esbuild jsx automatic matches Next's automatic JSX runtime (no React import needed).
export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
});
