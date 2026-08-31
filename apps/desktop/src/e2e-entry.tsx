/**
 * TEST-ONLY E2E bootstrap entry.
 *
 * This module is NEVER loaded by the normal production/dev entry. It is reached
 * only through index.e2e.html + vite.e2e.config.ts, and seeds the existing store
 * via `loadProject()` — no IPC command, window backdoor, shell hook, or normal
 * runtime behavior is added. See e2e/README.e2e.md.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { useStudio } from "./store";
// The E2E seed renders the SAME production App, so it must load the SAME global
// stylesheet. Without this, the harness renders unstyled: the timeline drops
// below the viewport and WebDriver pointer moves fail with "out of bounds".
import "./styles.css";
import fixtureProject from "../e2e/fixtures/project.json";
import sampleMp4Url from "../e2e/fixtures/sample.mp4?url";

function bootstrapE2E() {
  // Clone before replacing the test fixture sentinel so schema validation is
  // applied to a fresh project document on every E2E app launch.
  const project = JSON.parse(JSON.stringify(fixtureProject)) as {
    assets: Array<{ sourcePath: string }>;
  };
  project.assets = project.assets.map((asset) =>
    asset.sourcePath === "E2E_FIXTURE_SAMPLE_MP4" ? { ...asset, sourcePath: sampleMp4Url } : asset,
  );

  // Existing production store API, called only from this E2E-only entry.
  useStudio.getState().loadProject(project);

  const root = document.getElementById("root");
  if (!root) throw new Error("E2E: #root missing");
  ReactDOM.createRoot(root).render(React.createElement(App));
}

bootstrapE2E();
