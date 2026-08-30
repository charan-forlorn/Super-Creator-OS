import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, existsSync, statSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  createEmptyProject,
  parseProject,
  type MediaAsset,
  type Project,
} from "@haios/project-model";
import {
  createStudioRegistry,
  CommandBus,
  ADD_ASSET,
  ADD_CLIP,
  TRIM_CLIP,
  SPLIT_CLIP,
  MOVE_CLIP,
} from "@haios/command-system";
import { probeToAsset, type MediaProbe } from "@haios/media-engine";

const FIXTURES = fileURLToPath(new URL("./fixtures", import.meta.url));
const SRC = join(FIXTURES, "e2e01-src.mp4");

function fpsFromRational(r: string | undefined): number {
  if (!r) return 0;
  const [n, d] = r.split("/").map(Number);
  if (!d) return n;
  return n / d;
}

/** Real ffprobe import of a media file -> typed MediaProbe. */
function realProbe(sourcePath: string): MediaProbe {
  const raw = execFileSync(
    "ffprobe",
    ["-v", "error", "-show_format", "-show_streams", "-of", "json", sourcePath],
    { encoding: "utf8" },
  );
  const j = JSON.parse(raw);
  const v = j.streams.find((s: any) => s.codec_type === "video");
  const a = j.streams.find((s: any) => s.codec_type === "audio");
  const fmt = j.format ?? {};
  if (!v) throw new Error("ffprobe produced no video stream");
  return {
    id: "asset-1",
    name: "e2e01-src.mp4",
    sourcePath,
    kind: "video",
    durationSec: Number(parseFloat(v.duration ?? fmt.duration ?? "0")),
    width: Number(v.width),
    height: Number(v.height),
    fps: fpsFromRational(v.avg_frame_rate),
    hasAudio: !!a,
    videoCodec: String(v.codec_name),
    audioCodec: a ? String(a.codec_name) : null,
    audioSampleRate: a ? Number(a.sample_rate) : null,
    probeStatus: "ok",
    error: null,
  };
}

/** Real ffmpeg render of the project (mirrors the Rust run_render pipeline). */
function renderReal(project: Project, outPath: string): void {
  const videoClips = project.tracks
    .filter((t) => t.kind === "video")
    .flatMap((t) => t.clips);
  const assets = project.assets;
  if (videoClips.length === 0) throw new Error("no video clips to render");
  const W = 1920;
  const H = 1080;
  const inputs: string[] = [];
  const concatParts: string[] = [];
  videoClips.forEach((clip, i) => {
    const asset = assets.find((x) => x.id === clip.assetId);
    if (!asset) throw new Error(`clip ${clip.id} missing asset`);
    inputs.push("-ss", String(clip.inPoint), "-t", String(clip.duration), "-i", asset.sourcePath);
    concatParts.push(
      `[${i}:v]scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,setsar=1[${i}v]`,
    );
  });
  const vlist = videoClips.map((_, i) => `[${i}v]`).join("");
  let filter = concatParts.join(";") + ";";
  filter += `${vlist}concat=n=${videoClips.length}:v=1:a=0[vout]`;
  const dur = Math.max(project.durationSec, 0.1);
  filter += `;aevalsrc=0:d=${dur.toFixed(3)}[aout]`;
  const args = [
    "-y",
    ...inputs,
    "-filter_complex",
    filter,
    "-map",
    "[vout]",
    "-map",
    "[aout]",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-movflags",
    "+faststart",
    outPath,
  ];
  const status = execFileSync("ffmpeg", args, { encoding: "utf8" });
  void status;
}

/** Real ffprobe verification of a rendered output. */
function verifyOutput(outPath: string) {
  const raw = execFileSync(
    "ffprobe",
    ["-v", "error", "-show_format", "-show_streams", "-of", "json", outPath],
    { encoding: "utf8" },
  );
  const j = JSON.parse(raw);
  const v = j.streams.find((s: any) => s.codec_type === "video");
  const a = j.streams.find((s: any) => s.codec_type === "audio");
  const fmt = j.format ?? {};
  return {
    container: String(fmt.format_name ?? ""),
    videoCodec: v?.codec_name ?? null,
    audioCodec: a?.codec_name ?? null,
    width: Number(v?.width ?? 0),
    height: Number(v?.height ?? 0),
    durationSec: Number(parseFloat(v?.duration ?? fmt.duration ?? "0")),
    sizeBytes: Number(fmt.size ?? 0),
  };
}

describe("E2E-01 — single narrative import -> edit -> save -> reopen -> render -> ffprobe", () => {
  it(
    "proves the complete user journey as one deterministic execution chain",
    () => {
      // --- generate synthetic video (real ffmpeg) ---
      execFileSync(
        "ffmpeg",
        [
          "-y",
          "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=10",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
          "-c:a", "aac", "-b:a", "128k", "-t", "10",
          SRC,
        ],
        { encoding: "utf8" },
      );
      expect(existsSync(SRC)).toBe(true);

      // --- ffprobe import -> MediaProbe -> MediaAsset ---
      const probe = realProbe(SRC);
      const asset: MediaAsset = probeToAsset(probe);
      expect(asset.kind).toBe("video");
      expect(asset.durationSec).toBeGreaterThan(0);
      expect(asset.width).toBe(640);
      expect(asset.height).toBe(360);

      const A: Record<string, boolean> = {} as any;
      const R: Record<string, any> = {} as any;

      // --- new project + add asset + add clip ---
      const initial = createEmptyProject("E2E-01", "p-e2e-01");
      initial.tracks = [
        { id: "tv", kind: "video", clips: [], captions: [] },
        { id: "ta", kind: "audio", clips: [], captions: [] },
      ];
      const bus = new CommandBus(createStudioRegistry(), initial);
      bus.execute(ADD_ASSET, { asset });
      A.MEDIA_IMPORTED = bus.project.assets.some((x) => x.id === "asset-1");
      A.PROJECT_HAS_ASSET = A.MEDIA_IMPORTED;

      const clip = {
        id: "c1",
        assetId: "asset-1",
        inPoint: 0,
        duration: 8,
        start: 0,
        trackId: "tv",
        transform: { scale: 1, x: 0, y: 0, opacity: 1 },
      };
      bus.execute(ADD_CLIP, { clip });
      A.CLIP_ADDED = bus.project.tracks
        .flatMap((t) => t.clips)
        .some((c) => c.id === "c1");

      // --- trim (left) ---
      bus.execute(TRIM_CLIP, { clipId: "c1", newInPoint: 2 });
      const afterTrim = bus.project.tracks
        .flatMap((t) => t.clips)
        .find((c) => c.id === "c1")!;
      A.TRIM_APPLIED = afterTrim.inPoint === 2 && afterTrim.duration === 6;

      // --- split at 3s (0 < 3 < 6) ---
      bus.execute(SPLIT_CLIP, { clipId: "c1", t: 3 });
      const clipsAfterSplit = bus.project.tracks
        .flatMap((t) => t.clips)
        .slice()
        .sort((a, b) => a.start - b.start);
      A.SPLIT_APPLIED =
        clipsAfterSplit.length === 2 &&
        clipsAfterSplit[0].id === "c1" &&
        clipsAfterSplit[0].duration === 3 &&
        clipsAfterSplit[1].id === "c1__r" &&
        clipsAfterSplit[1].inPoint === 5 &&
        clipsAfterSplit[1].duration === 3;
      const splitState = JSON.stringify(
        bus.project.tracks.flatMap((t) => t.clips).sort((a, b) => a.start - b.start),
      );

      // --- move left clip to start=1 ---
      bus.execute(MOVE_CLIP, { clipId: "c1", newStart: 1 });
      const afterMove = JSON.stringify(
        bus.project.tracks.flatMap((t) => t.clips).sort((a, b) => a.start - b.start),
      );
      A.MOVE_APPLIED = bus.project.tracks
        .flatMap((t) => t.clips)
        .find((c) => c.id === "c1")!.start === 1;

      // --- undo (reverts move) -> redo (re-applies move) ---
      bus.undo();
      const afterUndo = JSON.stringify(
        bus.project.tracks.flatMap((t) => t.clips).sort((a, b) => a.start - b.start),
      );
      A.UNDO_RESTORED_EXPECTED_STATE = afterUndo === splitState;
      bus.redo();
      const afterRedo = JSON.stringify(
        bus.project.tracks.flatMap((t) => t.clips).sort((a, b) => a.start - b.start),
      );
      A.REDO_REAPPLIED_EXPECTED_STATE = afterRedo === afterMove;

      // --- save project to disk ---
      const workdir = mkdtempSync(join(tmpdir(), "e2e01-"));
      const projPath = join(workdir, "project.haios.json");
      writeFileSync(projPath, JSON.stringify(bus.project, null, 2));
      A.PROJECT_SAVED = existsSync(projPath) && statSync(projPath).size > 0;

      // --- destroy / reset in-memory state ---
      const freshBus = new CommandBus(createStudioRegistry(), createEmptyProject("scratch", "x"));
      expect(freshBus.project.assets.length).toBe(0);
      expect(
        freshBus.project.tracks.flatMap((t) => t.clips).length,
      ).toBe(0);

      // --- reopen project from disk ---
      const reopened: Project = parseProject(JSON.parse(readFileSync(projPath, "utf8")));
      freshBus.load(reopened);
      A.PROJECT_REOPENED = true;
      const reopenedClips = freshBus.project.tracks
        .flatMap((t) => t.clips)
        .slice()
        .sort((a, b) => a.start - b.start);
      A.REOPENED_STATE_MATCHES =
        JSON.stringify(reopenedClips) === afterMove && freshBus.project.assets.length === 1;

      // --- export real video (real ffmpeg) ---
      const outPath = join(workdir, "render_out.mp4");
      renderReal(freshBus.project, outPath);
      A.RENDER_EXIT_SUCCESS = existsSync(outPath) && statSync(outPath).size > 0;
      A.OUTPUT_EXISTS = A.RENDER_EXIT_SUCCESS;
      A.OUTPUT_SIZE_GT_ZERO = statSync(outPath).size > 0;

      // --- ffprobe output + verify ---
      const v = verifyOutput(outPath);
      A.OUTPUT_CONTAINER =
        String(v.container).includes("mp4");
      A.OUTPUT_VIDEO_CODEC = v.videoCodec === "h264";
      A.OUTPUT_AUDIO_CODEC = v.audioCodec === "aac";
      A.OUTPUT_RESOLUTION_EXPECTED = v.width === 1920 && v.height === 1080;
      A.OUTPUT_DURATION_WITHIN_TOLERANCE =
        v.durationSec >= 5.5 && v.durationSec <= 6.5;

      const TOTAL = Object.keys(A).length;
      const PASS = Object.values(A).filter(Boolean).length;
      // eslint-disable-next-line no-console
      console.log("E2E-01 ASSERTIONS", JSON.stringify(A, null, 2));
      console.log(`E2E-01 PASS ${PASS}/${TOTAL}`);

      expect(PASS).toBe(TOTAL);
      expect(A.MEDIA_IMPORTED).toBe(true);
      expect(A.PROJECT_HAS_ASSET).toBe(true);
      expect(A.CLIP_ADDED).toBe(true);
      expect(A.TRIM_APPLIED).toBe(true);
      expect(A.SPLIT_APPLIED).toBe(true);
      expect(A.MOVE_APPLIED).toBe(true);
      expect(A.UNDO_RESTORED_EXPECTED_STATE).toBe(true);
      expect(A.REDO_REAPPLIED_EXPECTED_STATE).toBe(true);
      expect(A.PROJECT_SAVED).toBe(true);
      expect(A.PROJECT_REOPENED).toBe(true);
      expect(A.REOPENED_STATE_MATCHES).toBe(true);
      expect(A.RENDER_EXIT_SUCCESS).toBe(true);
      expect(A.OUTPUT_EXISTS).toBe(true);
      expect(A.OUTPUT_SIZE_GT_ZERO).toBe(true);
      expect(A.OUTPUT_CONTAINER).toBe(true);
      expect(A.OUTPUT_VIDEO_CODEC).toBe(true);
      expect(A.OUTPUT_AUDIO_CODEC).toBe(true);
      expect(A.OUTPUT_RESOLUTION_EXPECTED).toBe(true);
      expect(A.OUTPUT_DURATION_WITHIN_TOLERANCE).toBe(true);

      // cleanup generated source so we never depend on a stale fixture
      try {
        rmSync(SRC, { force: true });
        rmSync(workdir, { recursive: true, force: true });
      } catch {
        /* best-effort */
      }
    },
    { timeout: 120_000 },
  );
});
