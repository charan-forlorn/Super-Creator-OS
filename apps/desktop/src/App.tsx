import { TopBar } from "./components/TopBar";
import { MediaPanel } from "./components/MediaPanel";
import { Preview } from "./components/Preview";
import { Inspector } from "./components/Inspector";
import { Timeline } from "./components/Timeline";
import { AICommandBar } from "./components/AICommandBar";
import { useKeyboard } from "./hooks/useKeyboard";
import { useStudio } from "./store";

export function App() {
  useKeyboard();
  const lastError = useStudio((s) => s.lastError);
  return (
    <div className="app-shell">
      <TopBar />
      <div className="app-body">
        <aside className="left-rail">
          <MediaPanel />
        </aside>
        <main className="center-stage">
          <Preview />
          <AICommandBar />
        </main>
        <aside className="right-rail">
          <Inspector />
        </aside>
      </div>
      <footer className="bottom-stage">
        <Timeline />
      </footer>
      {lastError && (
        <div className="error-toast" onClick={() => useStudio.setState({ lastError: null })}>
          {lastError}
        </div>
      )}
    </div>
  );
}
