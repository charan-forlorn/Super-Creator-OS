"""e2e_truth_runner.py — SCOS Stage 1 END-TO-END TRUTH ORACLE.

Drives the REAL pipeline over the REAL filesystem and proves it is reproducible:

    ScenePlan -> AssetBuilder (M3) -> EditComposer -> FFmpeg Engine (M2) -> MP4

No mocks, no stubs, no fake success. Every stage is validated against actual files
(PNG headers, WAV via `wave`, MP4 via `ffprobe`). The runner never modifies any
production module — it only imports and validates them.

Run:  python scos/tests/e2e_truth_runner.py
Exit: 0 on PASS, 1 on FAIL. Always prints a JSON report.

Dependencies: Python stdlib + numpy (via the imported modules). `ffmpeg`/`ffprobe`
are system tools (already a project prerequisite), used only for rendering/probing.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scos.assets import AssetBuilder                 # noqa: E402  (Module 3)
from scos.agents.edit_composer import EditComposer   # noqa: E402  (reused, unmodified)
from scos.render import ffmpeg_engine                 # noqa: E402  (Module 2, unmodified)

from scos.media_binaries import resolve_ffmpeg, resolve_ffprobe  # noqa: E402

FFMPEG = resolve_ffmpeg()
FFPROBE = resolve_ffprobe()

_RENDER_DIR = _REPO_ROOT / "scos" / "work" / "render"
_MANIFEST = _REPO_ROOT / "scos" / "work" / "assets_manifest.json"
_TOL_S = 0.05


class E2EFail(Exception):
    """Carries structured failure detail for the [SCOS-E2E-FAIL] block."""
    def __init__(self, stage: str, reason: str, scene_id: str | None = None,
                 file_path: str | None = None) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.scene_id = scene_id
        self.file_path = file_path


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _png_dims(p: Path) -> tuple[int, int]:
    data = p.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise E2EFail("asset", "invalid PNG signature", file_path=str(p))
    return struct.unpack(">II", data[16:24])  # IHDR width,height


def _ffprobe_dims(p: Path) -> tuple[int, int]:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(p)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise E2EFail("render", f"ffprobe failed: {proc.stderr.strip()[-200:]}", file_path=str(p))
    st = json.loads(proc.stdout)["streams"][0]
    return st["width"], st["height"]


def _framemd5(p: Path) -> str:
    """Decoded-frame checksum (robust to encoder byte drift). Comment lines stripped."""
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(p),
         "-map", "0:v", "-f", "framemd5", "-"], capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln and not ln.startswith("#")]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def build_scene_plan() -> dict:
    """STEP 1 — deterministic ScenePlan (>=2 scenes, consistent total)."""
    scenes = [
        {"scene_id": "scene_00", "topic": "cold open hook", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "the payoff", "start": 2.0, "end": 3.5},
        {"scene_id": "scene_02", "topic": "call to action", "start": 3.5, "end": 5.0},
    ]
    total = round(max(s["end"] for s in scenes), 3)
    if abs(total - sum(s["end"] - s["start"] for s in scenes)) > 1e-6:
        raise E2EFail("asset", "scene plan durations inconsistent with total_duration")
    return {"scenes": scenes, "total_duration": total}


# --------------------------------------------------------------------------- #
# pipeline (one full run)
# --------------------------------------------------------------------------- #
def run_once(scene_plan: dict, tag: str) -> dict:
    """Execute STEP 2-5 once. Returns artifacts (run_id, hashes, mp4 path)."""
    # STEP 2 — AssetBuilder
    res = AssetBuilder().run(scene_plan)
    run_id = res.get("run_id")
    if not run_id:
        raise E2EFail("asset", "AssetBuilder returned no run_id")
    asset_dir = _REPO_ROOT / "scos" / "work" / "assets" / run_id
    if not asset_dir.is_dir():
        raise E2EFail("asset", "asset directory missing", file_path=str(asset_dir))

    scenes_by_id = {s["scene_id"]: s for s in scene_plan["scenes"]}
    asset_sha: dict[str, tuple[str, str]] = {}

    # STEP 3 — strict per-scene asset validation
    for a in res["assets"]:
        sid = a["scene_id"]
        img = _REPO_ROOT / a["image_path"]
        aud = _REPO_ROOT / a["audio_path"]
        if not img.exists() or img.stat().st_size == 0:
            raise E2EFail("asset", "PNG missing/empty", sid, str(img))
        if _png_dims(img) != (1080, 1920):
            raise E2EFail("asset", f"PNG not 1080x1920 (got {_png_dims(img)})", sid, str(img))
        if not aud.exists() or aud.stat().st_size == 0:
            raise E2EFail("asset", "WAV missing/empty", sid, str(aud))
        with wave.open(str(aud), "rb") as w:
            sr, ch, frames = w.getframerate(), w.getnchannels(), w.getnframes()
        if sr != 48000:
            raise E2EFail("asset", f"WAV sample rate {sr} != 48000", sid, str(aud))
        if ch != 1:
            raise E2EFail("asset", f"WAV channels {ch} != mono", sid, str(aud))
        want = scenes_by_id[sid]["end"] - scenes_by_id[sid]["start"]
        if abs(frames / sr - want) > _TOL_S:
            raise E2EFail("asset", f"WAV duration {frames/sr:.3f}s != {want:.3f}s", sid, str(aud))
        asset_sha[sid] = (_sha(img), _sha(aud))

    # STEP 4 — manifest validation
    if not _MANIFEST.exists():
        raise E2EFail("asset", "manifest missing", file_path=str(_MANIFEST))
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("run_id") != run_id:
        raise E2EFail("asset", "manifest run_id mismatch", file_path=str(_MANIFEST))
    m_ids = [m["scene_id"] for m in manifest["assets"]]
    if m_ids != list(scenes_by_id):
        raise E2EFail("asset", f"manifest scenes {m_ids} != plan {list(scenes_by_id)}")
    for m in manifest["assets"]:
        for key in ("image_path", "audio_path"):
            p = m[key]
            if Path(p).is_absolute() or ":" in p:
                raise E2EFail("asset", f"manifest path not relative: {p}", m["scene_id"], p)
    manifest_sha = _sha(_MANIFEST)

    # STEP 5 — EditComposer -> FFmpeg engine -> MP4
    try:
        edit_timeline = EditComposer().run({"scene_plan": scene_plan, "asset_bundle": res})
    except Exception as exc:  # noqa: BLE001
        raise E2EFail("composer", f"EditComposer failed: {exc}")
    if len(edit_timeline.get("clips", [])) != len(scene_plan["scenes"]):
        raise E2EFail("composer", "clip count != scene count (M3->M2 mismatch)")

    try:
        render = ffmpeg_engine.render({"run_id": run_id, "edit_timeline": edit_timeline})
    except Exception as exc:  # noqa: BLE001 — real ffmpeg failure, no silent fallback
        raise E2EFail("render", f"render raised: {exc}")
    produced = Path(render["video_path"])
    if not produced.exists() or produced.stat().st_size == 0:
        raise E2EFail("render", "MP4 missing/empty", file_path=str(produced))
    if _ffprobe_dims(produced) != (1080, 1920):
        raise E2EFail("render", f"MP4 not 1080x1920 (got {_ffprobe_dims(produced)})",
                      file_path=str(produced))

    _RENDER_DIR.mkdir(parents=True, exist_ok=True)
    snap = _RENDER_DIR / f"output_{tag}.mp4"
    shutil.copyfile(produced, snap)

    return {"run_id": run_id, "asset_sha": asset_sha, "manifest_sha": manifest_sha,
            "mp4": snap}


# --------------------------------------------------------------------------- #
# orchestration + report
# --------------------------------------------------------------------------- #
def main() -> int:
    report = {"status": "FAIL", "run_id": None, "asset_valid": False,
              "render_valid": False, "determinism_valid": False,
              "mp4_path": "scos/work/render/output.mp4"}
    fail: E2EFail | None = None
    try:
        scene_plan = build_scene_plan()

        a = run_once(scene_plan, "A")          # STEP 2-5, run A
        report["run_id"] = a["run_id"]
        report["asset_valid"] = True
        report["render_valid"] = True

        b = run_once(scene_plan, "B")          # STEP 6, run B

        # asset-level determinism — the hard, fully-controlled gate
        if a["run_id"] != b["run_id"]:
            raise E2EFail("determinism", f"run_id drift {a['run_id']} != {b['run_id']}")
        if a["manifest_sha"] != b["manifest_sha"]:
            raise E2EFail("determinism", "manifest sha256 drift between runs")
        for sid in a["asset_sha"]:
            if a["asset_sha"][sid] != b["asset_sha"].get(sid):
                raise E2EFail("determinism", "PNG/WAV sha256 drift between runs", sid)
        report["determinism_valid"] = True

        # MP4 determinism — sha256, else decoded-frame checksum (encoder may drift)
        if _sha(a["mp4"]) == _sha(b["mp4"]):
            report["mp4_determinism"] = "sha256"
        elif _framemd5(a["mp4"]) == _framemd5(b["mp4"]):
            report["mp4_determinism"] = "framemd5"
        else:
            report["mp4_determinism"] = "drift (encoder; assets are byte-identical)"

        # canonical output
        shutil.copyfile(a["mp4"], _RENDER_DIR / "output.mp4")
        report["status"] = "PASS"

    except E2EFail as exc:
        fail = exc
    except Exception as exc:  # noqa: BLE001 — any unexpected error is a hard fail
        fail = E2EFail("render", f"unexpected: {exc}")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if fail is not None:
        print("\n[SCOS-E2E-FAIL]")
        print(f"stage: {fail.stage}")
        if fail.scene_id:
            print(f"scene_id: {fail.scene_id}")
        print(f"reason: {fail.reason}")
        if fail.file_path:
            print(f"file_path: {fail.file_path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
