import { create } from "zustand";
import {
  type Project,
  type Clip,
  type Caption,
  type ExportResolution,
  createEmptyProject,
  parseProject,
} from "@haios/project-model";
import {
  type CommandRegistry,
  CommandBus,
  createStudioRegistry,
  CommandBusValidationError,
  CommandError,
  ADD_CLIP,
  DELETE_CLIP,
  MOVE_CLIP,
  TRIM_CLIP,
  SET_CLIP_AUDIO,
  SET_CLIP_EFFECTS,
  SET_CLIP_TRANSITION,
  SET_CLIP_TRANSFORM,
  SPLIT_CLIP,
  ADD_CAPTION,
  PLACE_CAPTION,
  REMOVE_CAPTION,
  CHANGE_ASPECT,
  PLACE_PROBED_MEDIA,
  RELINK_MEDIA,
} from "@haios/command-system";
import {
  type AiEditPlan,
  planToCommands,
  AiPlanValidationError,
  AiSemanticError,
} from "@haios/ai-core";
import { type AIProvider, OfflineProvider, ProviderUnavailableError } from "@haios/ai-providers";
import type { MediaProbe } from "./bridge";
import type { MediaAnalysisResult } from "./mediaAnalysis";
import { PureMediaCache } from "@haios/media-engine";

/** R2.2 — deterministic, browser-safe cache lifecycle tracker (no fs IO). */
const mediaCache = new PureMediaCache("");

let clipCounter = 0;
let captionCounter = 0;
function uid(prefix: string): string {
  clipCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${clipCounter}`;
}

export interface AssetAnalysisState {
  sourcePath: string;
  status: "queued" | "analyzing" | MediaAnalysisResult["status"];
  probe?: MediaProbe;
  thumbnailPath?: string;
  proxyPath?: string;
  waveformPath?: string;
  error?: string;
}

export interface StudioState {
  project: Project;
  bus: CommandBus;
  registry: CommandRegistry;
  selectedClipId: string | null;
  /** R2.1 — multi-selection. `selectedClipId` mirrors the primary selection for
   *  single-clip consumers (Inspector, AICommandBar) so they need no changes. */
  selectedClipIds: string[];
  playheadSec: number;
  zoom: number;
  scrollSec: number;
  snapInterval: number;
  provider: AIProvider;
  thumbnails: Record<string, string>;
  /** Deterministically-cached preview proxy paths keyed by asset id (ROOT_CAUSE_3). */
  previewProxies: Record<string, string>;
  /** Deterministic media cache lifecycle state (HIT/MISS/STALE) keyed by cache key. */
  cacheState: Record<string, "missing" | "fresh" | "stale">;
  /** R2.3 — runtime-only derived analysis, never persisted into the project schema. */
  mediaAnalysis: Record<string, AssetAnalysisState>;
  lastError: string | null;
  dirty: boolean;

  newProject: () => void;
  loadProject: (raw: unknown) => void;
  markSaved: () => void;

  /** Atomic import + timeline placement (ROOT_CAUSE_1 fix). Returns the created clip id. */
  importProbedMedia: (probe: MediaProbe) => string | null;
  setThumbnail: (assetId: string, url: string) => void;
  setPreviewProxy: (assetId: string, proxyPath: string) => void;
  /** R2.2 — record a deterministic proxy cache entry + record its lifecycle state. */
  recordProxyCache: (sourcePath: string, codecSignature: string, revision: number) => void;
  /** R2.2 — record a deterministic thumbnail cache entry + record its lifecycle state. */
  recordThumbnailCache: (sourcePath: string, timeSec: number, revision: number) => void;
  /** R2.2 — invalidate cache entries for a source (proxy + thumbnails). */
  invalidateSourceCache: (sourcePath: string) => void;
  setMediaAnalysis: (assetId: string, state: AssetAnalysisState) => void;
  relinkMedia: (assetId: string, probe: MediaProbe) => boolean;

  selectClip: (id: string | null) => void;
  /** R2.1 — toggle/extend selection (multi-select). */
  toggleClipSelection: (id: string) => void;
  selectAllClips: () => void;
  clearClipSelection: () => void;
  setPlayhead: (sec: number) => void;
  setZoom: (z: number) => void;
  setScroll: (s: number) => void;

  addClip: (assetId: string, trackId: string, inPoint: number, duration: number, start: number) => void;
  deleteSelected: () => void;
  moveSelected: (newStart: number) => void;
  /** R2.1 — commit a group move (all selected clips shifted by delta seconds) as ONE undoable unit. */
  commitGroupMove: (deltaSec: number) => void;
  trimSelected: (newInPoint?: number, newSourceEnd?: number) => void;
  setSelectedAudio: (gainDb: number, muted: boolean) => boolean;
  setSelectedEffects: (brightness: number, contrast: number, saturation: number) => boolean;
  setSelectedTransition: (mode: "none" | "crossfade", duration?: number) => boolean;
  setSelectedTransform: (scale: number, x: number, y: number, opacity: number) => boolean;
  splitSelected: (t?: number) => void;
  duplicateSelected: () => void;
  addCaption: (trackId: string, text: string, start: number, duration: number) => void;
  placeCaption: (text: string, start: number, duration: number) => boolean;
  removeCaption: (captionId: string, trackId: string) => boolean;
  changeAspect: (ratio: ExportResolution) => void;

  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  runAiInstruction: (instruction: string) => Promise<AiEditPlan | { error: string }>;
}

function makeBus(): { bus: CommandBus; registry: CommandRegistry } {
  const registry = createStudioRegistry();
  const bus = new CommandBus(registry, createEmptyProject("Untitled", uid("proj")));
  return { bus, registry };
}

export const useStudio = create<StudioState>((set, get) => {
  const initial = makeBus();
  return {
    project: initial.bus.project,
    bus: initial.bus,
    registry: initial.registry,
    selectedClipId: null,
    selectedClipIds: [],
    playheadSec: 0,
    zoom: 1,
    scrollSec: 0,
    snapInterval: 1,
    provider: new OfflineProvider(),
    thumbnails: {},
    previewProxies: {},
    cacheState: {},
    mediaAnalysis: {},
    lastError: null,
    dirty: false,

    newProject: () => {
      const { bus, registry } = makeBus();
      mediaCache.clear();
      set({ project: bus.project, bus, registry, selectedClipId: null, playheadSec: 0, previewProxies: {}, thumbnails: {}, cacheState: {}, mediaAnalysis: {}, dirty: false, lastError: null });
    },

    loadProject: (raw) => {
      const p = parseProject(raw); // fail-closed on bad schema version
      const registry = createStudioRegistry();
      const bus = new CommandBus(registry, p);
      mediaCache.clear();
      set({ project: p, bus, registry, selectedClipId: null, playheadSec: 0, previewProxies: {}, thumbnails: {}, cacheState: {}, mediaAnalysis: {}, dirty: false, lastError: null });
    },

    markSaved: () => set({ dirty: false }),

    // ROOT_CAUSE_1 FIX — atomic import + placement.
    // A single CommandBus operation (PLACE_PROBED_MEDIA) adds the asset, ensures
    // the correct track exists, places the clip, and updates duration. The result
    // returns the created clipId so we can select it immediately from CURRENT
    // state. This removes the former race where the UI captured a stale
    // `project` snapshot before the asset (and its track) existed.
    importProbedMedia: (probe) => {
      if (probe.probeStatus !== "ok") {
        set({ lastError: `probe failed: ${probe.error ?? probe.probeStatus}` });
        return null;
      }
      try {
        const res = get().bus.execute<{ clipId?: string }>(PLACE_PROBED_MEDIA, {
          probe: {
            id: probe.id,
            name: probe.name,
            sourcePath: probe.sourcePath,
            kind: probe.kind,
            durationSec: probe.durationSec,
            width: probe.width,
            height: probe.height,
            fps: probe.fps,
            hasAudio: probe.hasAudio,
            videoCodec: probe.videoCodec,
            audioCodec: probe.audioCodec,
            probeStatus: probe.probeStatus,
          },
          place: true,
        });
        set({ project: get().bus.project, dirty: true, selectedClipId: res.clipId ?? null });
        return res.clipId ?? null;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return null;
      }
    },

    setThumbnail: (assetId, url) =>
      set((s) => ({ thumbnails: { ...s.thumbnails, [assetId]: url } })),

    // Record a generated H.264/AAC preview proxy for an asset (ROOT_CAUSE_3).
    // Original source path is never overwritten.
    setPreviewProxy: (assetId, proxyPath) =>
      set((s) => ({ previewProxies: { ...s.previewProxies, [assetId]: proxyPath } })),

    // R2.2 — record a deterministic proxy cache entry + its lifecycle state.
    recordProxyCache: (sourcePath, codecSignature, revision) => {
      const entry = mediaCache.recordProxy(sourcePath, codecSignature, revision);
      set((s) => ({ cacheState: { ...s.cacheState, [entry.key]: "fresh" } }));
    },

    // R2.2 — record a deterministic thumbnail cache entry + its lifecycle state.
    recordThumbnailCache: (sourcePath, timeSec, revision) => {
      const entry = mediaCache.recordThumbnail(sourcePath, timeSec, revision);
      set((s) => ({ cacheState: { ...s.cacheState, [entry.key]: "fresh" } }));
    },

    // R2.2 — invalidate every cache entry for a source (proxy + thumbnails).
    invalidateSourceCache: (sourcePath) => {
      const removed = mediaCache.invalidateSource(sourcePath);
      if (removed > 0) set({ cacheState: {} });
    },

    setMediaAnalysis: (assetId, state) =>
      set((state0) => ({ mediaAnalysis: { ...state0.mediaAnalysis, [assetId]: state } })),

    relinkMedia: (assetId, probe) => {
      const prior = get().project.assets.find((asset) => asset.id === assetId);
      if (!prior) {
        set({ lastError: `ASSET_NOT_FOUND: ${assetId}` });
        return false;
      }
      try {
        get().bus.execute(RELINK_MEDIA, { assetId, probe });
        mediaCache.invalidateSource(prior.sourcePath);
        set((state0) => {
          const thumbnails = { ...state0.thumbnails };
          const previewProxies = { ...state0.previewProxies };
          delete thumbnails[assetId];
          delete previewProxies[assetId];
          return {
            project: get().bus.project,
            thumbnails,
            previewProxies,
            cacheState: {},
            mediaAnalysis: {
              ...state0.mediaAnalysis,
              [assetId]: { sourcePath: probe.sourcePath, status: "queued", probe },
            },
            dirty: true,
            lastError: null,
          };
        });
        return true;
      } catch (error) {
        set({ lastError: (error as Error).message });
        return false;
      }
    },

    selectClip: (id) => set({ selectedClipId: id, selectedClipIds: id ? [id] : [] }),
    toggleClipSelection: (id) =>
      set((s) => {
        const has = s.selectedClipIds.includes(id);
        const next = has
          ? s.selectedClipIds.filter((x) => x !== id)
          : [...s.selectedClipIds, id];
        return { selectedClipIds: next, selectedClipId: next.length ? next[next.length - 1] : null };
      }),
    selectAllClips: () =>
      set((s) => ({
        selectedClipIds: s.project.tracks.flatMap((t) => t.clips.map((c) => c.id)),
        selectedClipId:
          s.project.tracks.flatMap((t) => t.clips.map((c) => c.id)).slice(-1)[0] ?? null,
      })),
    clearClipSelection: () => set({ selectedClipIds: [], selectedClipId: null }),
    setPlayhead: (sec) => set({ playheadSec: Math.max(0, sec) }),
    setZoom: (z) => set({ zoom: Math.max(0.1, Math.min(10, z)) }),
    setScroll: (s) => set({ scrollSec: Math.max(0, s) }),

    addClip: (assetId, trackId, inPoint, duration, start) => {
      const id = uid("clip");
      const clip: Clip = { id, assetId, inPoint, duration, start, trackId, transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false }, effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn: null };
      get().bus.execute(ADD_CLIP, { clip });
      set({ project: get().bus.project, dirty: true, selectedClipId: id });
    },

    deleteSelected: () => {
      const ids = get().selectedClipIds;
      if (ids.length === 0) return;
      try {
        // One undoable unit: deleting N selected clips collapses to a single undo.
        get().bus.batch(ids.map((id) => ({ commandType: DELETE_CLIP, payload: { clipId: id } })));
        set({ project: get().bus.project, selectedClipIds: [], selectedClipId: null, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    moveSelected: (newStart) => {
      const id = get().selectedClipId;
      if (!id) return;
      try {
        get().bus.execute(MOVE_CLIP, { clipId: id, newStart });
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    // R2.1 — shift every selected clip by `deltaSec` as ONE atomic, undoable group.
    // Preserves relative spacing by clamping the WHOLE group's minimum start to 0
    // (not each clip independently), so a drag near the left edge keeps ordering.
    // Fail-closed: if any clip is missing, the whole gesture is rejected.
    commitGroupMove: (deltaSec) => {
      const ids = get().selectedClipIds;
      if (ids.length === 0) return;
      const clips = get().project.tracks.flatMap((t) => t.clips);
      const found = ids
        .map((id) => clips.find((x) => x.id === id))
        .filter((c): c is NonNullable<typeof c> => c !== undefined);
      if (found.length === 0) return;
      const rawStarts = found.map((c) => c.start + deltaSec);
      const minRaw = Math.min(...rawStarts);
      const shift = minRaw < 0 ? -minRaw : 0; // lift the whole group so min >= 0
      const moves = found.map((c) => ({ clipId: c.id, newStart: c.start + deltaSec + shift }));
      try {
        get().bus.batch(moves.map((m) => ({ commandType: MOVE_CLIP, payload: m })));
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    setSelectedAudio: (gainDb, muted) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        get().bus.execute(SET_CLIP_AUDIO, { clipId: id, gainDb, muted });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    setSelectedEffects: (brightness, contrast, saturation) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        get().bus.execute(SET_CLIP_EFFECTS, { clipId: id, brightness, contrast, saturation });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    setSelectedTransition: (mode, duration) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        get().bus.execute(SET_CLIP_TRANSITION, { clipId: id, mode, duration });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    setSelectedTransform: (scale, x, y, opacity) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        get().bus.execute(SET_CLIP_TRANSFORM, { clipId: id, scale, x, y, opacity });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    trimSelected: (newInPoint, newSourceEnd) => {
      const id = get().selectedClipId;
      if (!id) return;
      try {
        get().bus.execute(TRIM_CLIP, { clipId: id, newInPoint, newSourceEnd });
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    splitSelected: (t) => {
      const ids = get().selectedClipIds;
      if (ids.length === 0) return;
      const clips = get().project.tracks.flatMap((tr) => tr.clips);
      // Split each selected clip at its LOCAL playhead offset (t is relative to
      // the clip start), clamped into (0, duration). All splits collapse into one undo.
      const splits = ids
        .map((id) => {
          const clip = clips.find((c) => c.id === id);
          if (!clip) return null;
          const local = t === undefined ? get().playheadSec - clip.start : t;
          if (!(local > 0 && local < clip.duration)) return null;
          return { clipId: id, t: local };
        })
        .filter((s): s is { clipId: string; t: number } => s !== null);
      if (splits.length === 0) return;
      try {
        get().bus.batch(splits.map((s) => ({ commandType: SPLIT_CLIP, payload: s })));
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    duplicateSelected: () => {
      const ids = get().selectedClipIds;
      if (ids.length === 0) return;
      const clips = get().project.tracks.flatMap((tr) => tr.clips);
      const copies: Clip[] = [];
      for (const id of ids) {
        const clip = clips.find((c) => c.id === id);
        if (!clip) continue;
        copies.push({
          ...clip,
          id: uid("clip"),
          start: clip.start + clip.duration,
          transform: { scale: 1, x: 0, y: 0, opacity: 1 },
        });
      }
      if (copies.length === 0) return;
      try {
        // Duplicate the whole selection as a single undoable group.
        get().bus.batch(copies.map((c) => ({ commandType: ADD_CLIP, payload: { clip: c } })));
        set({
          project: get().bus.project,
          selectedClipIds: copies.map((c) => c.id),
          selectedClipId: copies.length ? copies[copies.length - 1].id : null,
          dirty: true,
        });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    placeCaption: (text, start, duration) => {
      try {
        get().bus.execute(PLACE_CAPTION, { text, start, duration });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    removeCaption: (captionId, trackId) => {
      try {
        get().bus.execute(REMOVE_CAPTION, { captionId, trackId });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    addCaption: (trackId, text, start, duration) => {
      captionCounter += 1;
      const caption: Caption = { id: `cap-${captionCounter}`, text, start, duration, trackId, style: { x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.6 } };
      try {
        get().bus.execute(ADD_CAPTION, { caption });
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    changeAspect: (ratio) => {
      try {
        get().bus.execute(CHANGE_ASPECT, { ratio });
        set({ project: get().bus.project, dirty: true });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    undo: () => {
      if (get().bus.canUndo) {
        get().bus.undo();
        const id = get().selectedClipId;
        const stillThere = id && get().project.tracks.some((t) => t.clips.some((c) => c.id === id));
        mediaCache.clear();
        set({ project: get().bus.project, dirty: true, selectedClipId: stillThere ? id : null, mediaAnalysis: {}, thumbnails: {}, previewProxies: {}, cacheState: {} });
      }
    },

    redo: () => {
      if (get().bus.canRedo) {
        get().bus.redo();
        mediaCache.clear();
        set({ project: get().bus.project, dirty: true, mediaAnalysis: {}, thumbnails: {}, previewProxies: {}, cacheState: {} });
      }
    },

    canUndo: () => get().bus.canUndo,
    canRedo: () => get().bus.canRedo,

    runAiInstruction: async (instruction) => {
      const { provider, project, selectedClipId, registry } = get();
      let response;
      try {
        response = await provider.generate({
          instruction,
          context: { clipIds: selectedClipId ? [selectedClipId] : [], selectedClipId: selectedClipId ?? undefined },
        });
      } catch (e) {
        if (e instanceof ProviderUnavailableError) return { error: "AI provider unavailable" };
        return { error: (e as Error).message };
      }
      const plan = response.plan;
      let commands;
      try {
        commands = planToCommands(plan, project, registry);
      } catch (e) {
        if (e instanceof AiPlanValidationError) return { error: `plan invalid: ${e.message}` };
        if (e instanceof AiSemanticError) return { error: `plan rejected: ${e.message}` };
        if (e instanceof CommandError) return { error: `compile refused: ${e.message}` };
        if (e instanceof CommandBusValidationError) return { error: `command invalid: ${e.message}` };
        return { error: (e as Error).message };
      }
      for (const c of commands) {
        try {
          get().bus.execute(c.commandType, c.payload);
        } catch (e) {
          set({ lastError: (e as Error).message });
          return { error: `execution failed: ${(e as Error).message}` };
        }
      }
      set({ project: get().bus.project, dirty: true });
      return plan;
    },
  };
});
