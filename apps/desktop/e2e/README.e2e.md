# HAIOS AI Video Studio — GUI E2E Harness (R2.1)

Test-only automation that drives the **actual rendered editor** (WebView2) to
prove the R2.1 pointer/keyboard gates. This is NOT a CommandBus/Zustand/unit
test; it performs real gestures (Ctrl-click, drag, undo, keyboard shortcuts)
and asserts against the visible DOM.

## Architecture

- **Tauri 2** app under test + **WebDriver** via `@tauri-apps/wdio-service`.
- Deterministic fixture: `e2e/fixtures/sample.mp4` (H.264/AAC, 12s, 320×240)
  generated with ffmpeg.
- Deterministic project: `e2e/fixtures/project.json` (3 clips c0/c1/c2 on a
  video track at start 0/4/8).
- Test entry: `src/e2e-entry.tsx` seeds that project through the **existing**
  `useStudio.loadProject()` store action (no new IPC, no backdoor) and renders
  `App` with stable `data-testid`/`data-selected`/`data-start` attributes.
- Test-only build: `index.e2e.html` + `vite.e2e.config.ts` → `dist-e2e/`
  (separate from production `dist/`).
- Test: `e2e/r2.1.timeline.e2e.ts` (WebDriver, real DOM gestures).

## Production-safety guarantee

Normal `pnpm build` / `pnpm dev` use `index.html` → `src/main.tsx` and the
default `vite.config.ts`. They never reference `e2e-entry.tsx`, `index.e2e.html`,
or `dist-e2e/`. The seed hook is therefore **absent from the production bundle**.
Verified by `grep` — see "Production surface check" below.

## One-time setup (not run by default; requires network + heavy tooling)

The E2E devDependencies are intentionally NOT in `package.json` so the normal
production install stays clean and the production build never depends on them.
Install them ad-hoc only when you want to actually run the harness:

```
cd apps/desktop
pnpm add -D @tauri-apps/wdio-service @wdio/cli @wdio/globals @wdio/mocha-framework @wdio/spec-reporter @wdio/types
cargo install tauri-driver
```

Test-only build artifacts (`dist-e2e/`, `e2e/fixtures/*.mp4`) are gitignored.

## Run

```
pnpm e2e:build              # build dist-e2e/ (test-only frontend)
pnpm tauri build            # build the Tauri binary (uses dist-e2e if configured)
# or point the existing binary at dist-e2e via tauri.conf frontendDist
pnpm e2e:test               # wdio run wdio.conf.ts
```

`wdio.conf.ts` launches `src-tauri/target/release/haios-video-studio.exe` with
the E2E frontend and runs `e2e/r2.1.timeline.e2e.ts`.

## Production surface check (required)

After any change, confirm the seed hook is NOT in the production build:

```
pnpm build
grep -RIn "e2e-entry\|E2E_FIXTURE_SAMPLE_MP4\|bootstrapE2E" dist/ && echo "LEAK!" || echo "NORMAL_PRODUCTION_E2E_HOOK_REFERENCES=0"
```

Expected: `NORMAL_PRODUCTION_E2E_HOOK_REFERENCES=0`.

## Gates proven by the test

GUI_CLIPS_VISIBLE, GUI_MULTI_SELECT, GUI_GROUP_DRAG, GUI_GROUP_SPACING_PRESERVED,
GUI_GROUP_UNDO, GUI_GROUP_REDO, GUI_SELECT_ALL, GUI_KEYBOARD_NUDGE,
GUI_GROUP_DELETE, GUI_GROUP_DELETE_UNDO, GUI_GROUP_DUPLICATE, GUI_MULTI_SPLIT,
GUI_CLEAR_SELECTION, REAL_GUI_RUNTIME.
