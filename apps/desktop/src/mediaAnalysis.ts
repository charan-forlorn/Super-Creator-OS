import type { MediaProbe } from "./bridge";

export type MediaAnalysisStatus = "ready" | "missing" | "failed";

export interface MediaAnalysisResult {
  status: MediaAnalysisStatus;
  probe?: MediaProbe;
  thumbnailPath?: string;
  proxyPath?: string;
  waveformPath?: string;
  error?: string;
}

export interface MediaAnalysisDeps {
  probeMedia: (path: string) => Promise<MediaProbe>;
  ensureThumbnail: (path: string, timeSec: number) => Promise<string>;
  ensurePreviewProxy: (path: string, videoCodec: string | null, audioCodec: string | null) => Promise<string>;
  ensureWaveform: (path: string) => Promise<string>;
  previewNeedsProxy: (probe: { kind: string; videoCodec: string | null; audioCodec: string | null }) => boolean;
}

interface PendingTask<T> {
  run: () => Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}
export class BoundedTaskQueue {
  private active = 0;
  private readonly pending: PendingTask<unknown>[] = [];

  constructor(readonly maxConcurrency: number) {
    if (!Number.isInteger(maxConcurrency) || maxConcurrency < 1) {
      throw new Error("maxConcurrency must be a positive integer");
    }
  }

  enqueue<T>(run: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.pending.push({ run, resolve: resolve as (value: unknown) => void, reject } as PendingTask<unknown>);
      this.drain();
    });
  }

  get activeCount(): number {
    return this.active;
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  private drain(): void {
    while (this.active < this.maxConcurrency && this.pending.length > 0) {
      const task = this.pending.shift()!;
      this.active += 1;
      void task.run().then(task.resolve, task.reject).finally(() => {
        this.active -= 1;
        this.drain();
      });
    }
  }
}

export const mediaAnalysisQueue = new BoundedTaskQueue(2);
export async function analyzeMediaSource(sourcePath: string, deps: MediaAnalysisDeps): Promise<MediaAnalysisResult> {
  let probe: MediaProbe;
  try {
    probe = await deps.probeMedia(sourcePath);
  } catch (error) {
    return { status: "failed", error: (error as Error).message };
  }
  if (probe.probeStatus === "missing") {
    return { status: "missing", probe, error: probe.error ?? "media source missing" };
  }
  if (probe.probeStatus !== "ok") {
    return { status: "failed", probe, error: probe.error ?? probe.probeStatus };
  }

  const result: MediaAnalysisResult = { status: "ready", probe };
  try {
    result.thumbnailPath = await deps.ensureThumbnail(sourcePath, Math.min(1, probe.durationSec / 2));
  } catch {
    // Thumbnail is derived media; analysis remains valid without it.
  }
  if (deps.previewNeedsProxy({ kind: probe.kind, videoCodec: probe.videoCodec, audioCodec: probe.audioCodec })) {
    try {
      result.proxyPath = await deps.ensurePreviewProxy(sourcePath, probe.videoCodec, probe.audioCodec);
    } catch {
      // Proxy generation failure does not erase valid source metadata.
    }
  }
  if (probe.hasAudio) {
    try {
      result.waveformPath = await deps.ensureWaveform(sourcePath);
    } catch {
      // Waveform is optional derived media.
    }
  }
  return result;
}
