const RECENT_PROJECTS_KEY = "haios.videoStudio.recentProjects.v1";
const MAX_RECENT_PROJECTS = 8;

export function mergeRecentProjects(current: string[], path: string): string[] {
  const target = path.trim();
  if (!target) return current.slice(0, MAX_RECENT_PROJECTS);
  const key = target.toLocaleLowerCase();
  return [target, ...current.filter((item) => item.toLocaleLowerCase() !== key)]
    .slice(0, MAX_RECENT_PROJECTS);
}

export function projectFileLabel(path: string): string {
  const normalized = path.replaceAll("\\", "/");
  return normalized.split("/").filter(Boolean).at(-1) ?? path;
}

export function readRecentProjects(): string[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_PROJECTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function rememberRecentProject(path: string): string[] {
  const next = mergeRecentProjects(readRecentProjects(), path);
  if (typeof localStorage !== "undefined") {
    try {
      localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
    } catch {
      // Recent-project persistence is convenience state; never block editing.
    }
  }
  return next;
}

export function forgetRecentProject(path: string): string[] {
  const key = path.toLocaleLowerCase();
  const next = readRecentProjects().filter((item) => item.toLocaleLowerCase() !== key);
  if (typeof localStorage !== "undefined") {
    try {
      localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
    } catch {
      // Best-effort cleanup only.
    }
  }
  return next;
}
