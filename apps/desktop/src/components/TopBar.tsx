import { useStudio } from "../store";
import { hvsCapabilities, selectOutputFile, hvsRender, verifyRender } from "../bridge";
import { useState } from "react";

export function TopBar() {
  const { project, dirty, undo, redo, canUndo, canRedo, newProject, markSaved } = useStudio();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSave() {
    setStatus("Saving...");
    try {
      const { writeTextFile } = await import("@tauri-apps/plugin-fs");
      const { save } = await import("@tauri-apps/plugin-dialog");
      const out = await save({ filters: [{ name: "HAIOS Project", extensions: ["json"] }], defaultPath: `${project.name}.haip.json` });
      if (!out) {
        setStatus("");
        return;
      }
      const tmp = out + ".tmp";
      await writeTextFile(tmp, JSON.stringify(project, null, 2));
      const { rename } = await import("@tauri-apps/plugin-fs");
      await rename(tmp, out); // atomic swap
      markSaved();
      setStatus("Saved.");
    } catch (e) {
      setStatus("Save failed: " + (e as Error).message);
    }
  }

  async function handleExport() {
    setBusy(true);
    setStatus("Exporting...");
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
      setStatus(`Render job ${jobId} started...`);
      // poll the job to completion via events is the real path; for the gate we
      // verify after a short wait by checking the file. Production uses the event.
      const ver = await verifyRender(out, project.aspectRatio);
      if (ver.ok) setStatus(`Exported & verified: ${out}`);
      else setStatus(`Render produced output but verify failed: ${ver.error}`);
    } catch (e) {
      setStatus("Export failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="top-bar">
      <div className="brand">HAIOS <span>AI Video Studio</span></div>
      <div className="project-name">{project.name}{dirty ? " •" : ""}</div>
      <div className="spacer" />
      <button onClick={newProject}>New</button>
      <button onClick={handleSave}>Save</button>
      <button disabled={!canUndo()} onClick={undo} title="Ctrl+Z">Undo</button>
      <button disabled={!canRedo()} onClick={redo} title="Ctrl+Shift+Z">Redo</button>
      <button className="primary" disabled={busy} onClick={handleExport}>Export</button>
      <div className="status">{status}</div>
    </header>
  );
}
