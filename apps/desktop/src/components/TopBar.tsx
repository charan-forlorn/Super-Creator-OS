import { useEffect, useRef, useState } from "react";
import { useStudio } from "../store";
import {
  autosaveProject,
  cancelRender,
  clearProjectAutosave,
  hvsCapabilities,
  hvsRender,
  latestProjectAutosave,
  listenRenderProgress,
  openProjectFile,
  saveProjectFile,
  selectOutputFile,
} from "../bridge";
import {
  forgetRecentProject,
  projectFileLabel,
  readRecentProjects,
  rememberRecentProject,
} from "../projectLifecycle";
import {
  applyRenderProgress,
  createRenderSession,
  isRenderTerminal,
  renderStatusText,
  type RenderSession,
} from "../renderLifecycle";

async function confirmDiscard(message: string): Promise<boolean> {
  const { confirm } = await import("@tauri-apps/plugin-dialog");
  return confirm(message, { title: "HAIOS AI Video Studio", kind: "warning" });
}

async function selectProjectToOpen(): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: false,
    filters: [{ name: "HAIOS Project", extensions: ["json"] }],
  });
  return Array.isArray(selected) ? selected[0] ?? null : selected;
}

async function selectProjectSavePath(defaultName: string): Promise<string | null> {
  const { save } = await import("@tauri-apps/plugin-dialog");
  return save({
    filters: [{ name: "HAIOS Project", extensions: ["json"] }],
    defaultPath: `${defaultName}.haip.json`,
  });
}

export function TopBar() {
  const {
    project,
    projectPath,
    dirty,
    undo,
    redo,
    canUndo,
    canRedo,
    newProject,
    loadProject,
    markSaved,
  } = useStudio();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [renderSession, setRenderSession] = useState<RenderSession | null>(null);
  const renderSessionRef = useRef<RenderSession | null>(null);
  const [recentProjects, setRecentProjects] = useState<string[]>(() => readRecentProjects());

  async function persistProject(path: string) {
    const snapshotProject = project;
    const snapshotUpdatedAt = project.updatedAt;
    setStatus("Saving...");
    try {
      await saveProjectFile(path, JSON.stringify(snapshotProject, null, 2));
      markSaved(path, snapshotUpdatedAt);
      const current = useStudio.getState();
      const stillCurrent = current.project.id === snapshotProject.id && current.project.updatedAt === snapshotUpdatedAt;
      if (stillCurrent) {
        await clearProjectAutosave(snapshotProject.id).catch(() => false);
      }
      setRecentProjects(rememberRecentProject(path));
      setStatus(stillCurrent
        ? `Saved: ${projectFileLabel(path)}`
        : `Saved snapshot: ${projectFileLabel(path)} — newer changes remain unsaved.`);
    } catch (error) {
      setStatus(`Save failed: ${(error as Error).message}`);
    }
  }

  async function handleSave() {
    if (projectPath) {
      await persistProject(projectPath);
      return;
    }
    await handleSaveAs();
  }

  async function handleSaveAs() {
    const path = await selectProjectSavePath(project.name);
    if (path) await persistProject(path);
  }

  async function openProjectAt(path: string) {
    const previousProjectId = project.id;
    setStatus("Opening project...");
    try {
      const rawText = await openProjectFile(path);
      const raw = JSON.parse(rawText);
      loadProject(raw, path, false);
      await clearProjectAutosave(previousProjectId).catch(() => false);
      setRecentProjects(rememberRecentProject(path));
      setStatus(`Opened: ${projectFileLabel(path)}`);
    } catch (error) {
      setRecentProjects(forgetRecentProject(path));
      setStatus(`Open failed: ${(error as Error).message}`);
    }
  }

  async function handleOpen() {
    if (dirty && !(await confirmDiscard("Discard current unsaved changes and open another project?"))) {
      return;
    }
    const path = await selectProjectToOpen();
    if (path) await openProjectAt(path);
  }

  async function handleNew() {
    if (dirty && !(await confirmDiscard("Discard current unsaved changes and create a new project?"))) {
      return;
    }
    await clearProjectAutosave(project.id).catch(() => false);
    newProject();
    setStatus("New project created.");
  }

  async function handleRecent(path: string) {
    if (!path) return;
    if (dirty && !(await confirmDiscard("Discard current unsaved changes and open the recent project?"))) {
      return;
    }
    await openProjectAt(path);
  }

  useEffect(() => {
    if (!dirty) return;
    const autosaveProjectId = project.id;
    const timer = window.setTimeout(() => {
      autosaveProject(autosaveProjectId, JSON.stringify(project), projectPath)
        .then(() => {
          if (useStudio.getState().project.id !== autosaveProjectId) {
            return clearProjectAutosave(autosaveProjectId).then(() => undefined);
          }
          return undefined;
        })
        .catch((error) => {
          setStatus(`Autosave failed: ${(error as Error).message}`);
        });
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [dirty, project, projectPath]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!("__TAURI_INTERNALS__" in window)) return;
      try {
        const envelope = await latestProjectAutosave();
        if (!envelope || cancelled) return;
        const recover = await confirmDiscard(
          `Recover unsaved changes from ${projectFileLabel(envelope.projectPath ?? envelope.projectId)}?`,
        );
        if (cancelled) return;
        if (!recover) {
          await clearProjectAutosave(envelope.projectId).catch(() => false);
          return;
        }
        const raw = JSON.parse(envelope.projectJson);
        loadProject(raw, envelope.projectPath, true);
        if (envelope.projectPath) setRecentProjects(rememberRecentProject(envelope.projectPath));
        setStatus("Recovered autosaved project. Save to confirm the recovered state.");
      } catch (error) {
        if (!cancelled) setStatus(`Recovery failed: ${(error as Error).message}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadProject]);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let disposed = false;
    void listenRenderProgress((progress) => {
      const current = renderSessionRef.current;
      if (current?.busy && current.jobId !== progress.jobId) return;
      const base = current?.jobId === progress.jobId
        ? current
        : createRenderSession(progress.jobId, progress.outputPath ?? "");
      const next = applyRenderProgress(base, progress);
      renderSessionRef.current = next;
      setRenderSession(next);
      setBusy(next.busy);
      setStatus(renderStatusText(progress));
    }).then((dispose) => {
      if (disposed) dispose();
      else unlisten = dispose;
    }).catch(() => undefined);
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let disposed = false;
    void (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const appWindow = getCurrentWindow();
        unlisten = await appWindow.onCloseRequested(async (event) => {
          if (!useStudio.getState().dirty) return;
          event.preventDefault();
          const close = await confirmDiscard(
            "This project has unsaved changes. Close the app? Autosave remains available for recovery.",
          );
          if (close) await appWindow.destroy();
        });
        if (disposed) unlisten();
      } catch {
        // Non-Tauri test/browser runtime.
      }
    })();
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  async function handleExport() {
    if (renderSessionRef.current?.busy) return;
    setBusy(true);
    setStatus("Preparing export...");
    try {
      const caps = await hvsCapabilities();
      if (!caps.ffmpeg) {
        setStatus("ffmpeg not available");
        setBusy(false);
        return;
      }
      const out = await selectOutputFile();
      if (!out) {
        setStatus("");
        setBusy(false);
        return;
      }
      const jobId = await hvsRender(JSON.stringify(project), out, project.aspectRatio);
      const observed = renderSessionRef.current;
      if (!observed || observed.jobId !== jobId) {
        const queued = createRenderSession(jobId, out);
        renderSessionRef.current = queued;
        setRenderSession(queued);
        setStatus("Export queued...");
      } else if (isRenderTerminal(observed.status)) {
        setBusy(false);
      }
    } catch (error) {
      setBusy(false);
      setStatus(`Export failed: ${(error as Error).message}`);
    }
  }

  async function handleCancelExport() {
    const active = renderSessionRef.current;
    if (!active?.busy) return;
    setStatus("Cancelling export...");
    try {
      await cancelRender(active.jobId);
    } catch (error) {
      if (renderSessionRef.current?.busy) {
        setStatus(`Cancel failed: ${(error as Error).message}`);
      }
    }
  }

  return (
    <header className="top-bar">
      <div className="brand">HAIOS <span>AI Video Studio</span></div>
      <div className="project-name" title={projectPath ?? "Unsaved project"}>
        {project.name}{dirty ? " •" : ""}
      </div>
      <div className="spacer" />
      <button disabled={busy} onClick={handleNew}>New</button>
      <button disabled={busy} onClick={handleOpen}>Open</button>
      <select
        className="recent-projects"
        aria-label="Open recent project"
        defaultValue=""
        disabled={busy || recentProjects.length === 0}
        onChange={(event) => {
          const path = event.currentTarget.value;
          event.currentTarget.value = "";
          void handleRecent(path);
        }}
      >
        <option value="">Recent</option>
        {recentProjects.map((path) => (
          <option key={path} value={path}>{projectFileLabel(path)}</option>
        ))}
      </select>
      <button disabled={busy} onClick={handleSave}>Save</button>
      <button disabled={busy} onClick={handleSaveAs}>Save As</button>
      <button disabled={busy || !canUndo()} onClick={undo} title="Ctrl+Z">Undo</button>
      <button disabled={busy || !canRedo()} onClick={redo} title="Ctrl+Shift+Z">Redo</button>
      {renderSession?.busy ? (
        <>
          <progress className="render-progress" max={1} value={renderSession.progress} aria-label="Export progress" />
          <button onClick={handleCancelExport}>Cancel Export</button>
        </>
      ) : null}
      <button className="primary" disabled={busy} onClick={handleExport}>Export</button>
      <div className="status">{status}</div>
    </header>
  );
}
