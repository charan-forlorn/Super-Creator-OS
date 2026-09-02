import { create } from "zustand";
import {
  type Project,
  type Clip,
  type Caption,
  type Track,
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
  MOVE_CLIP_ACROSS_TRACKS,
  TRIM_CLIP,
  RIPPLE_DELETE_CLIPS,
  RIPPLE_TRIM_CLIP,
  TIMELINE_INSERT_ASSET,
  TIMELINE_OVERWRITE_ASSET,
  SET_CLIP_AUDIO,
  SET_CLIP_EFFECTS,
  SET_CLIP_SPEED,
  SET_CLIP_TRANSITION,
  SET_CLIP_TRANSFORM,
  SPLIT_CLIP,
  ADD_CAPTION,
  PLACE_CAPTION,
  REMOVE_CAPTION,
  CHANGE_ASPECT,
  PLACE_PROBED_MEDIA,
  RELINK_MEDIA,
  ADD_TRACK,
  REMOVE_TRACK,
  REORDER_TRACK,
  SET_TRACK_CONTROLS,
} from "@haios/command-system";
import { buildCrossTrackMovePlan } from "./crossTrackMove";
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
  /** Runtime-only media-bin selection for insert/overwrite editing. */
  selectedAssetId: string | null;
  /** Runtime-only canonical target track for UI editing operations. */
  selectedTrackId: string | null;
  playheadSec: number;
  /** Runtime-only shuttle direction: -1 reverse, 0 paused, 1 forward. */
  transportRate: -1 | 0 | 1;
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
  /** Persisted project file currently associated with the editing document. */
  projectPath: string | null;

  newProject: () => void;
  loadProject: (raw: unknown, projectPath?: string | null, dirty?: boolean) => void;
  markSaved: (projectPath?: string | null, expectedUpdatedAt?: string) => void;

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
  selectAsset: (id: string | null) => void;
  selectTrack: (id: string | null) => void;
  addTrack: (kind: Track["kind"]) => string | null;
  removeSelectedTrack: () => boolean;
  moveSelectedTrack: (direction: -1 | 1) => boolean;
  setSelectedTrackControls: (controls: Partial<Pick<Track, "visible" | "muted" | "locked">>) => boolean;
  insertSelectedAssetAtPlayhead: () => boolean;
  overwriteSelectedAssetAtPlayhead: () => boolean;

  selectClip: (id: string | null) => void;
  /** R2.1 — toggle/extend selection (multi-select). */
  toggleClipSelection: (id: string) => void;
  setClipSelection: (ids: string[], extend?: boolean) => void;
  selectAllClips: () => void;
  clearClipSelection: () => void;
  setPlayhead: (sec: number) => void;
  stepPlayhead: (direction: -1 | 1, coarse?: boolean) => void;
  jumpPlayhead: (target: "start" | "end") => void;
  setTransportRate: (rate: -1 | 0 | 1) => void;
  toggleTransport: () => void;
  fitTimelineZoom: (viewportWidthPx: number) => void;
  setZoom: (z: number) => void;
  setScroll: (s: number) => void;

  addClip: (assetId: string, trackId: string, inPoint: number, duration: number, start: number) => void;
  deleteSelected: () => void;
  rippleDeleteSelected: () => void;
  moveSelected: (newStart: number, targetTrackId?: string) => boolean;
  /** R2.1 — commit a group move (all selected clips shifted by delta seconds) as ONE undoable unit. */
  commitGroupMove: (deltaSec: number, anchorClipId?: string, anchorTargetTrackId?: string) => boolean;
  trimSelected: (newInPoint?: number, newSourceEnd?: number) => void;
  rippleTrimSelected: (newInPoint?: number, newSourceEnd?: number) => void;
  setSelectedAudio: (gainDb: number, muted: boolean) => boolean;
  setSelectedEffects: (brightness: number, contrast: number, saturation: number) => boolean;
  setSelectedSpeed: (playbackRate: number) => boolean;
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

function navigationFrameStep(project: Project, playheadSec: number): number {
  const videoClips = project.tracks.filter((track) => track.kind === "video").flatMap((track) => track.clips);
  const active = videoClips.find((clip) => playheadSec >= clip.start && playheadSec < clip.start + clip.duration);
  const activeFps = active ? project.assets.find((asset) => asset.id === active.assetId)?.fps : undefined;
  const fallbackFps = project.assets.find((asset) => asset.kind === "video" && asset.fps)?.fps;
  const fps = activeFps ?? fallbackFps ?? 30;
  return 1 / fps;
}

function clampTimelineSec(sec: number, durationSec: number): number {
  return Math.min(Math.max(0, durationSec), Math.max(0, sec));
}

function compatibleTargetTrackId(project: Project, selectedTrackId: string | null, kind: Track["kind"]): string | undefined {
  if (!selectedTrackId) return undefined;
  const track = project.tracks.find((candidate) => candidate.id === selectedTrackId);
  return track?.kind === kind ? track.id : undefined;
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
    selectedAssetId: null,
    selectedTrackId: null,
    playheadSec: 0,
    transportRate: 0,
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
    projectPath: null,

    newProject: () => {
      const { bus, registry } = makeBus();
      mediaCache.clear();
      set({ project: bus.project, bus, registry, selectedClipId: null, selectedClipIds: [], selectedAssetId: null, selectedTrackId: null, playheadSec: 0, transportRate: 0, previewProxies: {}, thumbnails: {}, cacheState: {}, mediaAnalysis: {}, dirty: false, projectPath: null, lastError: null });
    },

    loadProject: (raw, projectPath = null, dirty = false) => {
      const p = parseProject(raw); // fail-closed on bad schema version
      const registry = createStudioRegistry();
      const bus = new CommandBus(registry, p);
      mediaCache.clear();
      set({ project: p, bus, registry, selectedClipId: null, selectedClipIds: [], selectedAssetId: null, selectedTrackId: null, playheadSec: 0, transportRate: 0, previewProxies: {}, thumbnails: {}, cacheState: {}, mediaAnalysis: {}, dirty, projectPath, lastError: null });
    },

    markSaved: (projectPath, expectedUpdatedAt) => set((state) => ({
      dirty: expectedUpdatedAt !== undefined && state.project.updatedAt !== expectedUpdatedAt
        ? state.dirty
        : false,
      projectPath: projectPath === undefined ? state.projectPath : projectPath,
    })),

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
          targetTrackId: compatibleTargetTrackId(get().project, get().selectedTrackId, probe.kind === "audio" ? "audio" : "video"),
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

    selectAsset: (id) => set((state) => {
      if (id === null) return { selectedAssetId: null, lastError: null };
      if (!state.project.assets.some((asset) => asset.id === id)) {
        return { selectedAssetId: state.selectedAssetId, lastError: `ASSET_NOT_FOUND: ${id}` };
      }
      return { selectedAssetId: id, lastError: null };
    }),

    selectTrack: (id) => set((state) => {
      if (id === null) return { selectedTrackId: null, lastError: null };
      if (!state.project.tracks.some((track) => track.id === id)) {
        return { selectedTrackId: state.selectedTrackId, lastError: `TRACK_NOT_FOUND: ${id}` };
      }
      return { selectedTrackId: id, lastError: null };
    }),

    addTrack: (kind) => {
      const id = uid(`track-${kind}`);
      const track: Track = { id, kind, clips: [], captions: [], visible: true, muted: false, locked: false };
      try {
        get().bus.execute(ADD_TRACK, { track });
        set({ project: get().bus.project, selectedTrackId: id, dirty: true, lastError: null });
        return id;
      } catch (error) { set({ lastError: (error as Error).message }); return null; }
    },
    removeSelectedTrack: () => {
      const id = get().selectedTrackId;
      if (!id) { set({ lastError: "SELECT_TRACK_REQUIRED" }); return false; }
      try {
        get().bus.execute(REMOVE_TRACK, { trackId: id });
        set({ project: get().bus.project, selectedTrackId: null, selectedClipId: null, selectedClipIds: [], dirty: true, lastError: null });
        return true;
      } catch (error) { set({ lastError: (error as Error).message }); return false; }
    },

    moveSelectedTrack: (direction) => {
      const id = get().selectedTrackId;
      if (!id) { set({ lastError: "SELECT_TRACK_REQUIRED" }); return false; }
      const index = get().project.tracks.findIndex((track) => track.id === id);
      const toIndex = index + direction;
      if (index < 0 || toIndex < 0 || toIndex >= get().project.tracks.length) return false;
      try {
        get().bus.execute(REORDER_TRACK, { trackId: id, toIndex });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (error) { set({ lastError: (error as Error).message }); return false; }
    },
    setSelectedTrackControls: (controls) => {
      const id = get().selectedTrackId;
      if (!id) { set({ lastError: "SELECT_TRACK_REQUIRED" }); return false; }
      try {
        get().bus.execute(SET_TRACK_CONTROLS, { trackId: id, ...controls });
        set({ project: get().bus.project, dirty: true, lastError: null });
        return true;
      } catch (error) { set({ lastError: (error as Error).message }); return false; }
    },

    insertSelectedAssetAtPlayhead: () => {
      const assetId = get().selectedAssetId;
      if (!assetId) {
        set({ lastError: "SELECT_MEDIA_ASSET_REQUIRED" });
        return false;
      }
      const clipId = uid("clip");
      try {
        get().bus.execute(TIMELINE_INSERT_ASSET, {
          assetId, clipId, atSec: get().playheadSec,
          targetTrackId: compatibleTargetTrackId(get().project, get().selectedTrackId, get().project.assets.find((asset) => asset.id === assetId)?.kind === "audio" ? "audio" : "video"),
        });
        set({ project: get().bus.project, selectedClipId: clipId, selectedClipIds: [clipId], dirty: true, lastError: null });
        return true;
      } catch (error) {
        set({ lastError: (error as Error).message });
        return false;
      }
    },

    overwriteSelectedAssetAtPlayhead: () => {
      const assetId = get().selectedAssetId;
      if (!assetId) {
        set({ lastError: "SELECT_MEDIA_ASSET_REQUIRED" });
        return false;
      }
      const clipId = uid("clip");
      try {
        get().bus.execute(TIMELINE_OVERWRITE_ASSET, {
          assetId, clipId, atSec: get().playheadSec,
          targetTrackId: compatibleTargetTrackId(get().project, get().selectedTrackId, get().project.assets.find((asset) => asset.id === assetId)?.kind === "audio" ? "audio" : "video"),
        });
        set({ project: get().bus.project, selectedClipId: clipId, selectedClipIds: [clipId], dirty: true, lastError: null });
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
    setClipSelection: (ids, extend = false) =>
      set((s) => {
        const valid = new Set(s.project.tracks.flatMap((t) => t.clips.map((c) => c.id)));
        const incoming = ids.filter((id, index) => valid.has(id) && ids.indexOf(id) === index);
        const next = extend
          ? [...s.selectedClipIds, ...incoming.filter((id) => !s.selectedClipIds.includes(id))]
          : incoming;
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
    stepPlayhead: (direction, coarse = false) => set((state) => {
      const step = coarse ? 1 : navigationFrameStep(state.project, state.playheadSec);
      return { playheadSec: clampTimelineSec(state.playheadSec + direction * step, state.project.durationSec) };
    }),
    jumpPlayhead: (target) => set((state) => ({ playheadSec: target === "start" ? 0 : Math.max(0, state.project.durationSec) })),
    setTransportRate: (rate) => set({ transportRate: rate }),
    toggleTransport: () => set((state) => ({ transportRate: state.transportRate === 0 ? 1 : 0 })),
    fitTimelineZoom: (viewportWidthPx) => set((state) => {
      if (!Number.isFinite(viewportWidthPx) || viewportWidthPx <= 64) return { lastError: "TIMELINE_VIEWPORT_INVALID" };
      const totalSec = Math.max(state.project.durationSec, 10) + 5;
      const zoom = Math.max(0.25, Math.min(4, (viewportWidthPx - 64) / (totalSec * 80)));
      return { zoom, scrollSec: 0 };
    }),
    setZoom: (z) => set({ zoom: Math.max(0.1, Math.min(10, z)) }),
    setScroll: (s) => set({ scrollSec: Math.max(0, s) }),

    addClip: (assetId, trackId, inPoint, duration, start) => {
      const id = uid("clip");
      const clip: Clip = { id, assetId, inPoint, duration, start, trackId, transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false }, effects: { brightness: 0, contrast: 1, saturation: 1 }, playbackRate: 1, transitionIn: null };
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

    rippleDeleteSelected: () => {
      const ids = get().selectedClipIds;
      if (ids.length === 0) return;
      try {
        get().bus.execute(RIPPLE_DELETE_CLIPS, { clipIds: ids });
        set({ project: get().bus.project, selectedClipIds: [], selectedClipId: null, dirty: true, lastError: null });
      } catch (e) {
        set({ lastError: (e as Error).message });
      }
    },

    moveSelected: (newStart, targetTrackId) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        const current = get().project.tracks.flatMap((track) => track.clips).find((clip) => clip.id === id);
        if (!current) throw new Error(`CROSS_TRACK_SELECTED_CLIP_NOT_FOUND: ${id}`);
        if (targetTrackId && targetTrackId !== current.trackId) {
          const plan = buildCrossTrackMovePlan(get().project, [id], id, newStart - current.start, targetTrackId);
          get().bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: plan.moves });
          set({ project: get().bus.project, dirty: true, lastError: null, selectedTrackId: plan.primaryDestinationTrackId });
        } else {
          get().bus.execute(MOVE_CLIP, { clipId: id, newStart });
          set({ project: get().bus.project, dirty: true, lastError: null });
        }
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
      }
    },

    // R2.1 — shift every selected clip by `deltaSec` as ONE atomic, undoable group.
    // Preserves relative spacing by clamping the WHOLE group's minimum start to 0
    // (not each clip independently), so a drag near the left edge keeps ordering.
    // Fail-closed: if any clip is missing, the whole gesture is rejected.
    commitGroupMove: (deltaSec, anchorClipId, anchorTargetTrackId) => {
      const ids = get().selectedClipIds;
      const selectedPrimaryId = get().selectedClipId;
      const primary = anchorClipId ?? selectedPrimaryId;
      if (ids.length === 0 || !primary) return false;
      try {
        const plan = buildCrossTrackMovePlan(get().project, ids, primary, deltaSec, anchorTargetTrackId);
        if (plan.vertical) {
          get().bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: plan.moves });
          const selectedPrimaryDestination = plan.moves.find((move) => move.clipId === selectedPrimaryId)?.targetTrackId ?? plan.primaryDestinationTrackId;
          set({ project: get().bus.project, dirty: true, lastError: null, selectedTrackId: selectedPrimaryDestination });
        } else {
          get().bus.batch(plan.moves.map(({ clipId, newStart }) => ({ commandType: MOVE_CLIP, payload: { clipId, newStart } })));
          set({ project: get().bus.project, dirty: true, lastError: null });
        }
        return true;
      } catch (e) {
        set({ lastError: (e as Error).message });
        return false;
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

    setSelectedSpeed: (playbackRate) => {
      const id = get().selectedClipId;
      if (!id) return false;
      try {
        get().bus.execute(SET_CLIP_SPEED, { clipId: id, playbackRate });
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

    rippleTrimSelected: (newInPoint, newSourceEnd) => {
      const id = get().selectedClipId;
      if (!id) return;
      try {
        get().bus.execute(RIPPLE_TRIM_CLIP, { clipId: id, newInPoint, newSourceEnd });
        set({ project: get().bus.project, dirty: true, lastError: null });
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
        get().bus.execute(PLACE_CAPTION, { text, start, duration, targetTrackId: compatibleTargetTrackId(get().project, get().selectedTrackId, "text") });
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
        const project = get().bus.project;
        const selectedTrack = id ? project.tracks.find((track) => track.clips.some((clip) => clip.id === id)) : undefined;
        mediaCache.clear();
        set({ project, dirty: true, selectedClipId: selectedTrack ? id : null, selectedTrackId: selectedTrack?.id ?? get().selectedTrackId, mediaAnalysis: {}, thumbnails: {}, previewProxies: {}, cacheState: {} });
      }
    },

    redo: () => {
      if (get().bus.canRedo) {
        get().bus.redo();
        const project = get().bus.project;
        const id = get().selectedClipId;
        const selectedTrack = id ? project.tracks.find((track) => track.clips.some((clip) => clip.id === id)) : undefined;
        mediaCache.clear();
        set({ project, dirty: true, selectedTrackId: selectedTrack?.id ?? get().selectedTrackId, mediaAnalysis: {}, thumbnails: {}, previewProxies: {}, cacheState: {} });
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
