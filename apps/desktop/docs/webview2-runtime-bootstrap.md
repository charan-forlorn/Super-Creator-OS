# R2.0 — Reproducible Fixed WebView2 Runtime Bootstrap

This document closes the **R1 build-reproducibility gap** described in the R2
operator contract §7. The Microsoft WebView2 **Fixed Version Runtime** is what
the Tauri `fixedRuntime` bundle mode loads, because the machine's Evergreen
WebView2 registration is unreliable. It is intentionally **not committed**
(>250 MB), so a deterministic acquisition + integrity mechanism is required.

## Pinned configuration (single source of truth)

All values are pinned in `scripts/webview2-runtime.checksum.json`:

| Field | Value |
| --- | --- |
| Product | `Microsoft.WebView2.FixedVersionRuntime` |
| Version | `151.0.4129.107` |
| Arch | `x64` |
| Extracted dir | `src-tauri/Microsoft.WebView2.FixedVersionRuntime.151.0.4129.107.x64/` |
| Official source | `https://msedgedl.blob.core.windows.net/webview/151.0.4129.107/Microsoft.WebView2.FixedVersionRuntime.151.0.4129.107.x64.cab` |
| Integrity target | `msedgewebview2.exe` |
| Expected SHA-256 | `fe7922326f2a1d3188454ba5502861253223d5da10d9da0b858f9b10f3e01468` |

The version/architecture/official-source triple matches what `tauri.conf.json`
references under `bundle.windows.webviewInstallMode.path`, so verification and
bundling stay consistent.

## Why integrity is enforced on the extracted binary (not the CAB)

Microsoft does **not** publish a checksum for the Fixed Version CAB at the
official endpoint. To avoid trusting an unverified transport file, we verify the
**actual artifact Tauri loads** — `msedgewebview2.exe` inside the extracted
runtime — and pin its SHA-256 from the R1-sealed, battle-tested runtime image.
The expected hash was computed and cross-checked with two independent tools
(`certutil` and Node `crypto`) on 2026-08-31.

This is **fail-closed**: any drift in the host binary fails verification and
blocks the build bootstrap. No untrusted mirror is permitted — the download URL
is constrained to the official `msedgedl.blob.core.windows.net` host.

## Commands

```bash
# Acquire/refresh the runtime (idempotent; no-op if already verified).
pnpm webview2:bootstrap

# Verify only the current extracted runtime against the pin.
pnpm webview2:verify

# Run the pure-node R2.0 reproducible-baseline test suite.
pnpm webview2:verify:test
```

`scripts/webview2-bootstrap.mjs` is the acquisition mechanism; `scripts/webview2-verify.mjs`
is the integrity gate (also invoked by `pnpm build`-adjacent CI). The test file
`scripts/webview2-bootstrap.test.mjs` asserts the real on-disk + pinned state
(no mocks).

## Failure handling

| Condition | Behavior |
| --- | --- |
| Runtime dir missing | FAIL with explicit `webview2:bootstrap` instruction |
| Host binary integrity mismatch | FAIL — refuse to bootstrap unverified runtime |
| Download fails (no egress) | FAIL — only the official Microsoft source is allowed |
| Extraction tool missing (`expand.exe`/`cabextract`) | FAIL — no silent fallback |
| CAB checksum unavailable | Accepted (documented) — extracted-binary hash is authoritative |

## Git hygiene

The extracted runtime directory is excluded from version control:

```
# .gitignore (line ~95)
apps/desktop/src-tauri/Microsoft.WebView2.FixedVersionRuntime.*/
```

No 250 MB runtime is ever committed. Only the manifest, bootstrap, verify, and
test scripts (tiny) are tracked.

## Reproducibility guarantee (R2.0 hard gates)

| Gate | Status |
| --- | --- |
| `WEBVIEW_FIXED_VERSION_PINNED=TRUE` | ✅ pinned in `webview2-runtime.checksum.json` |
| `WEBVIEW_BOOTSTRAP_REPRODUCIBLE=TRUE` | ✅ deterministic `webview2:bootstrap.mjs` |
| `NO_250MB_RUNTIME_COMMITTED=TRUE` | ✅ gitignored |
| `BUILD_FROM_FRESH_RUNTIME_STATE=PASS` | ✅ `webview2:verify` + `pnpm build` + `cargo check` green |
