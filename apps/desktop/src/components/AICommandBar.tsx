import { useState } from "react";
import { useStudio } from "../store";

export function AICommandBar() {
  const { runAiInstruction, selectedClipId } = useStudio();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string>("");

  async function run() {
    if (!text.trim()) return;
    setBusy(true);
    setResult("");
    try {
      const res = await runAiInstruction(text);
      if ("error" in res) setResult("⚠ " + res.error);
      else setResult("✓ Executed plan: " + res.operations.map((o) => o.tool).join(", "));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ai-command-bar">
      <span className="ai-prompt-label">AI</span>
      <input
        className="ai-input"
        placeholder={selectedClipId ? `Command the selected clip (e.g. "split the selected clip at 4 seconds")` : 'Select a clip, then type a command'}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") run(); }}
      />
      <button className="ai-run" disabled={busy} onClick={run}>{busy ? "…" : "Run"}</button>
      {result && <span className={`ai-result ${result.startsWith("⚠") ? "err" : "ok"}`}>{result}</span>}
    </div>
  );
}
