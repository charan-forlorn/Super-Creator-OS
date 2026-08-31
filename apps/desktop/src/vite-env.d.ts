/// <reference types="vite/client" />

// Test-only asset imports (used solely by src/e2e-entry.tsx, which is never
// referenced by the production entry). The e2e entry resolves fixtures via
// `new URL(..., import.meta.url)`, which Vite handles natively.
declare module "*?url" {
  const src: string;
  export default src;
}
