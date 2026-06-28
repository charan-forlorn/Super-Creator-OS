"""SCOS Stage 2.4 — System Qualification & Certification Suite.

The Stage-2 Gate. A READ-ONLY certification harness that exercises the whole SCOS
platform end-to-end across 10 qualifications and emits a deterministic
`certification_report.json` + a 0–100 score. It calls only public APIs and runs the
existing test scripts; it modifies no production module.

Determinism: `qualification_time` is fixed (default 0), a fixed clock is injected into
the learning loop, and all suite-owned stores live in an isolated, cleared-at-start
`scos/work/qualification/` directory.

Run: python scos/qualification/system_qualification.py
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics"))
sys.path.insert(0, str(_REPO_ROOT / "scos" / "learning"))

from scos.assets.asset_builder import AssetBuilder                # v1  # noqa: E402
from scos.assets.asset_builder_v2 import AssetBuilderV2           # v2  # noqa: E402
from scos.agents.edit_composer import EditComposer               # noqa: E402
from scos.render import ffmpeg_engine                             # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine           # noqa: E402
import feedback_engine as FE                                      # noqa: E402
import learning_coordinator as LC                                 # noqa: E402
import learning_policy as LP                                      # noqa: E402

_WORK_DIR = _REPO_ROOT / "scos" / "work" / "qualification"
_FIXED_TS = 0

# 10 qualifications -> report keys (10 pts each).
_TEST_KEYS = ["pipeline", "determinism", "learning", "rollback", "audit",
              "regression", "api", "persistence", "dependency", "self_learning"]

SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "gaming", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "gaming", "start": 2.0, "end": 3.5},
        {"scene_id": "scene_02", "topic": "gaming", "start": 3.5, "end": 5.0},
    ],
    "total_duration": 5.0,
}


# --------------------------------------------------------------------------- #
# small stdlib helpers
# --------------------------------------------------------------------------- #
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ffprobe_dims(p: Path) -> tuple:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(p)],
        capture_output=True, text=True).stdout
    st = json.loads(out)["streams"][0]
    return st["width"], st["height"]


def _framemd5(p: Path) -> str:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(p),
                          "-map", "0:v", "-f", "framemd5", "-"], capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln and not ln.startswith("#")]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _style_profile(style_id="qstyle", ct="gaming", palette=None, freq=320.0, pacing=1.0):
    return {"style_id": style_id, "content_type": ct,
            "avg_color_palette": palette or [200, 60, 40], "audio_frequency_bias": freq,
            "scene_pacing_profile": pacing, "retention_score": 0.9, "created_at": 1000}


def _asset_hashes(res):
    return {a["scene_id"]: (_sha(_REPO_ROOT / a["image_path"]), _sha(_REPO_ROOT / a["audio_path"]))
            for a in res["assets"]}


# --------------------------------------------------------------------------- #
# suite
# --------------------------------------------------------------------------- #
class SystemQualification:
    def __init__(self, now_fn=None, work_dir: Path | str = _WORK_DIR) -> None:
        self.now_fn = now_fn or (lambda: _FIXED_TS)
        self.work_dir = Path(work_dir)
        self.style_store = self.work_dir / "style_memory.json"
        self.feedback_store = self.work_dir / "feedback_log.json"
        # coordinator writes learning_state.json / style_history.json / learning_audit.json here

    # ---- pipeline primitives (public APIs only) ----
    def _fresh_engine(self) -> StyleMemoryEngine:
        if self.style_store.exists():
            self.style_store.unlink()
        eng = StyleMemoryEngine(self.style_store)
        eng.record_video_metrics(_style_profile())
        return eng

    def _engine_at(self, sub: str):
        """Isolated engine + coordinator dir for a single qualification, so version
        history / audit / state never bleed across qualifications."""
        d = self.work_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        store = d / "style_memory.json"
        if store.exists():
            store.unlink()
        eng = StyleMemoryEngine(store)
        eng.record_video_metrics(_style_profile())
        return eng, d

    def _generate(self, eng) -> dict:
        return AssetBuilderV2(eng).run(SCENE_PLAN)

    def _render(self, res) -> Path:
        edit_timeline = EditComposer().run({"scene_plan": SCENE_PLAN, "asset_bundle": res})
        out = ffmpeg_engine.render({"run_id": res["run_id"], "edit_timeline": edit_timeline})
        return Path(out["video_path"])

    # =================== Q1 ===================
    def q1_pipeline(self):
        eng = self._fresh_engine()
        res = self._generate(eng)
        mp4 = self._render(res)
        manifest = json.loads((_REPO_ROOT / res["manifest_path"]).read_text(encoding="utf-8"))
        ok = (mp4.exists() and mp4.stat().st_size > 0
              and _ffprobe_dims(mp4) == (1080, 1920)
              and all((_REPO_ROOT / a["image_path"]).exists()
                      and (_REPO_ROOT / a["audio_path"]).exists() for a in res["assets"])
              and manifest.get("engine") == "asset_builder_v2"
              and manifest.get("style_enabled") is True
              and len(manifest["assets"]) == len(SCENE_PLAN["scenes"]))
        return ok, {"mp4": str(mp4), "scenes": len(res["assets"])}

    # =================== Q2 ===================
    def q2_determinism(self):
        runs = []
        for _ in range(3):
            eng = self._fresh_engine()
            res = self._generate(eng)
            mp4 = self._render(res)
            runs.append({
                "run_id": res["run_id"],
                "assets": _asset_hashes(res),
                "manifest": _sha(_REPO_ROOT / res["manifest_path"]),
                "mp4_sha": _sha(mp4),
                "mp4_frames": _framemd5(mp4),
            })
        a = runs[0]
        ok = all(r["run_id"] == a["run_id"] and r["assets"] == a["assets"]
                 and r["manifest"] == a["manifest"] for r in runs)
        mp4_same = all(r["mp4_sha"] == a["mp4_sha"] for r in runs) or \
            all(r["mp4_frames"] == a["mp4_frames"] for r in runs)
        return (ok and mp4_same), {"run_id": a["run_id"],
                                   "mp4_determinism": "sha256" if all(r["mp4_sha"] == a["mp4_sha"] for r in runs) else "framemd5"}

    # =================== Q3 ===================
    def q3_learning(self):
        eng, d = self._engine_at("q3")
        coord = LC.LearningCoordinator(eng, now_fn=self.now_fn, work_dir=d)
        sid = "qstyle"
        confidences, in_bounds = [], True
        feedbacks = [
            {"q": 0.9, "r": 0.9, "e": 0.2, "s": 0.2},   # apply freq + palette, pacing up
            {"q": 0.9, "r": 0.3, "e": 0.8, "s": 0.9},   # pacing down
            {"q": 0.9, "r": 0.95, "e": 0.2, "s": 0.9},  # pacing up + freq
            {"q": 0.4, "r": 0.9, "e": 0.2, "s": 0.2},   # reject (low quality)
            {"q": 0.9, "r": 0.9, "e": 0.2, "s": 0.2},
            {"q": 0.9, "r": 0.5, "e": 0.9, "s": 0.9},   # no-op
        ]
        for fb in feedbacks:
            style = next(s for s in eng.list_styles() if s["style_id"] == sid)
            coord.coordinate({"feedback": _mk_feedback(**fb), "style_profile": style})
            state = json.loads((d / "learning_state.json").read_text(encoding="utf-8"))
            confidences.append(state["confidence"])
            cur = next(s for s in eng.list_styles() if s["style_id"] == sid)
            if not (LP.FREQ_MIN <= cur["audio_frequency_bias"] <= LP.FREQ_MAX
                    and LP.PACING_MIN <= cur["scene_pacing_profile"] <= LP.PACING_MAX
                    and all(LP.RGB_MIN <= c <= LP.RGB_MAX for c in cur["avg_color_palette"])):
                in_bounds = False
        bounded = all(0.0 <= c <= 1.0 for c in confidences)
        return (bounded and in_bounds), {"confidences": confidences}

    # =================== Q4 ===================
    def q4_rollback(self):
        eng, d = self._engine_at("q4")
        coord = LC.LearningCoordinator(eng, now_fn=self.now_fn, work_dir=d)
        sid = "qstyle"
        original = next(s for s in eng.list_styles() if s["style_id"] == sid)
        # learn twice (two applies)
        for fb in ({"q": 0.9, "r": 0.95, "e": 0.2, "s": 0.2},
                   {"q": 0.9, "r": 0.95, "e": 0.2, "s": 0.2}):
            style = next(s for s in eng.list_styles() if s["style_id"] == sid)
            coord.coordinate({"feedback": _mk_feedback(**fb), "style_profile": style})
        coord.rollback(sid, 0)
        restored = next(s for s in eng.list_styles() if s["style_id"] == sid)
        hist = json.loads((d / "style_history.json").read_text(encoding="utf-8"))
        v0 = hist[sid][0]["profile"]
        audit = json.loads((d / "learning_audit.json").read_text(encoding="utf-8"))
        ok = (all(restored[k] == v0[k] for k in ("avg_color_palette", "audio_frequency_bias", "scene_pacing_profile"))
              and all(restored[k] == original[k] for k in ("avg_color_palette", "audio_frequency_bias", "scene_pacing_profile"))
              and [s["version"] for s in hist[sid]] == [0, 1, 2]
              and any(e["decision"] == "ROLLBACK" for e in audit))
        return ok, {"versions": [s["version"] for s in hist[sid]]}

    # =================== Q5 ===================
    def q5_audit(self):
        eng, d = self._engine_at("q5")
        coord = LC.LearningCoordinator(eng, now_fn=self.now_fn, work_dir=d)
        sid = "qstyle"
        # diverse decisions: APPLY, REJECT, ROLLBACK
        coord.coordinate({"feedback": _mk_feedback(0.9, 0.95, 0.2, 0.2),
                          "style_profile": next(s for s in eng.list_styles() if s["style_id"] == sid)})
        coord.coordinate({"feedback": _mk_feedback(0.2, 0.9, 0.2, 0.2),
                          "style_profile": next(s for s in eng.list_styles() if s["style_id"] == sid)})
        coord.rollback(sid, 0)

        audit = json.loads((d / "learning_audit.json").read_text(encoding="utf-8"))
        schema = {"audit_id", "decision", "reason", "style_before", "style_after",
                  "feedback_summary", "timestamp"}
        ids = [e["audit_id"] for e in audit]
        decisions = {e["decision"] for e in audit}
        ok = (bool(audit)
              and all(schema <= set(e) for e in audit)
              and len(ids) == len(set(ids))                       # unique
              and all(isinstance(e["timestamp"], int) for e in audit)
              and {"APPLY", "REJECT", "ROLLBACK"} <= decisions)
        return ok, {"entries": len(audit), "unique_ids": len(set(ids)), "decisions": sorted(decisions)}

    # =================== Q6 ===================
    def q6_regression(self):
        suites = [
            "scos/tests/e2e_truth_runner.py",
            "scos/assets/tests/test_asset_builder.py",
            "scos/assets/tests/test_asset_builder_v2.py",
            "scos/memory/tests/test_style_memory.py",
            "scos/analytics/tests/test_feedback_engine.py",
            "scos/learning/tests/test_learning_coordinator.py",
        ]
        results = {}
        for s in suites:
            rc = subprocess.run([sys.executable, s], cwd=str(_REPO_ROOT),
                                capture_output=True, text=True).returncode
            results[s] = (rc == 0)
        return all(results.values()), results

    # =================== Q7 ===================
    def q7_persistence(self):
        # Produce all 5 canonical stores in an isolated dir via public APIs only.
        eng, d = self._engine_at("q7")
        coord = LC.LearningCoordinator(eng, now_fn=self.now_fn, work_dir=d)
        coord.coordinate({"feedback": _mk_feedback(0.9, 0.95, 0.2, 0.2),
                          "style_profile": next(s for s in eng.list_styles() if s["style_id"] == "qstyle")})
        res = self._generate(eng)
        mp4 = self._render(res)
        fe = FE.FeedbackEngine(store_path=d / "feedback_log.json")
        result = fe.evaluate({"run_id": res["run_id"], "mp4_path": str(mp4),
                              "manifest_path": res["manifest_path"], "assets": res["assets"],
                              "content_type": "gaming"})
        fe.persist_feedback(result)
        fe.persist_feedback(result)   # idempotent upsert -> proves no-duplicate

        files = ["style_memory.json", "learning_state.json", "style_history.json",
                 "learning_audit.json", "feedback_log.json"]
        details = {}
        ok = True
        for f in files:
            p = d / f
            if not p.exists():
                ok = False; details[f] = "missing"; continue
            try:
                raw = p.read_text(encoding="utf-8")
                data = json.loads(raw)
            except json.JSONDecodeError:
                ok = False; details[f] = "invalid json"; continue
            if json.loads(raw) != data:                      # reload-recoverable
                ok = False; details[f] = "not recoverable"; continue
            if isinstance(data, list) and data and isinstance(data[0], dict):
                key = "audit_id" if "audit_id" in data[0] else ("run_id" if "run_id" in data[0] else None)
                if key:
                    keys = [x[key] for x in data]
                    if len(keys) != len(set(keys)):
                        ok = False; details[f] = "duplicates"; continue
            details[f] = "ok"
        return ok, details

    # =================== Q8 ===================
    def q8_dependency(self):
        stdlib = set(getattr(sys, "stdlib_module_names", set()))
        firstparty = {p.stem for p in (_REPO_ROOT / "scos").rglob("*.py")}
        allowed = stdlib | {"numpy", "scos"} | firstparty
        violations = {}
        for py in (_REPO_ROOT / "scos").rglob("*.py"):
            parts = set(py.parts)
            if "tests" in parts or "qualification" in parts or "__pycache__" in parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                violations[str(py)] = "syntax"; continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = a.name.split(".")[0]
                        if top not in allowed:
                            violations.setdefault(str(py), []).append(top)
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue  # relative -> first-party
                    top = (node.module or "").split(".")[0]
                    if top and top not in allowed:
                        violations.setdefault(str(py), []).append(top)
        return (not violations), {"violations": violations}

    # =================== Q9 ===================
    def q9_api(self):
        def params(fn):
            return [p for p in inspect.signature(fn).parameters if p != "self"]
        expected = {
            "AssetBuilder.run": (AssetBuilder.run, ["scene_plan", "run_id"]),
            "AssetBuilderV2.run": (AssetBuilderV2.run, ["scene_plan", "run_id"]),
            "StyleMemoryEngine.record_video_metrics": (StyleMemoryEngine.record_video_metrics, ["style_profile"]),
            "StyleMemoryEngine.get_style": (StyleMemoryEngine.get_style, ["content_type"]),
            "StyleMemoryEngine.update_style": (StyleMemoryEngine.update_style, ["style_id", "updates"]),
            "StyleMemoryEngine.list_styles": (StyleMemoryEngine.list_styles, []),
            "FeedbackEngine.evaluate": (FE.FeedbackEngine.evaluate, ["run_bundle"]),
            "FeedbackEngine.persist_feedback": (FE.FeedbackEngine.persist_feedback, ["result"]),
            "LearningCoordinator.coordinate": (LC.LearningCoordinator.coordinate, ["payload"]),
            "LearningCoordinator.rollback": (LC.LearningCoordinator.rollback, ["style_id", "version"]),
        }
        mismatches = {name: params(fn) for name, (fn, exp) in expected.items() if params(fn) != exp}
        return (not mismatches), {"mismatches": mismatches}

    # =================== Q10 ===================
    def q10_self_learning(self):
        def one_loop(sub):
            eng, d = self._engine_at(sub)
            gen1 = _asset_hashes(self._generate(eng))
            res1 = self._generate(eng)
            mp4 = self._render(res1)
            fe = FE.FeedbackEngine(store_path=d / "feedback_log.json")
            feedback = fe.evaluate({"run_id": res1["run_id"], "mp4_path": str(mp4),
                                    "manifest_path": res1["manifest_path"], "assets": res1["assets"],
                                    "content_type": "gaming"})
            coord = LC.LearningCoordinator(eng, now_fn=self.now_fn, work_dir=d)
            style = next(s for s in eng.list_styles() if s["style_id"] == "qstyle")
            decision = coord.coordinate({"feedback": feedback, "style_profile": style})
            gen2 = _asset_hashes(self._generate(eng))
            cur = next(s for s in eng.list_styles() if s["style_id"] == "qstyle")
            within = (LP.FREQ_MIN <= cur["audio_frequency_bias"] <= LP.FREQ_MAX
                      and LP.PACING_MIN <= cur["scene_pacing_profile"] <= LP.PACING_MAX
                      and all(LP.RGB_MIN <= c <= LP.RGB_MAX for c in cur["avg_color_palette"]))
            return decision["decision"], gen1, gen2, within

        d1, g1a, g1b, w1 = one_loop("q10a")
        d2, g2a, g2b, w2 = one_loop("q10b")
        applied = d1 in ("APPLY", "CLAMP")
        affected = (g1a != g1b)                       # learning changed next generation
        deterministic = (d1 == d2 and g1a == g2a and g1b == g2b)
        return (applied and affected and deterministic and w1 and w2), {
            "decision": d1, "affected_next_gen": affected, "bounded": w1 and w2}

    # ---- orchestration ----
    def run_all(self) -> dict:
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        steps = [self.q1_pipeline, self.q2_determinism, self.q3_learning, self.q4_rollback,
                 self.q5_audit, self.q6_regression, self.q7_persistence, self.q8_dependency,
                 self.q9_api, self.q10_self_learning]
        tests, details = {}, {}
        for key, fn in zip(_TEST_KEYS, steps):
            try:
                passed, detail = fn()
            except Exception as exc:  # noqa: BLE001 — any failure is a hard non-cert
                passed, detail = False, {"error": f"{type(exc).__name__}: {exc}"}
            tests[key] = bool(passed)
            details[key] = detail

        score = sum(10 for v in tests.values() if v)
        status = "PASS" if score == 100 else "FAIL"
        report = {"status": status, "qualified_stage": "Stage 2", "system_version": "SCOS",
                  "qualification_time": _FIXED_TS, "tests": tests}

        report_path = self.work_dir / "certification_report.json"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False),
                               encoding="utf-8")
        self._details = details
        self._score = score
        return report


def _mk_feedback(q, r, e, s):
    return {
        "run_id": "qrun", "retention_score": r, "engagement_score": e,
        "style_match_score": s, "quality_score": q,
        "derived_style_updates": {"content_type": "gaming",
                                  "audio_frequency_bias_delta": 40.0,
                                  "scene_pacing_delta": 0.2,
                                  "palette_shift_hint": [10, 10, 10]},
    }


def _print_console(report: dict, score: int) -> None:
    print("=" * 36)
    print("SCOS SYSTEM QUALIFICATION")
    print("=" * 36)
    print(report["status"])
    print(f"Certification Score: {score}/100")
    print(f"System Certified: {'YES' if report['status'] == 'PASS' else 'NO'}")
    print(f"Ready for Stage 3: {'YES' if report['status'] == 'PASS' else 'NO'}")


def main() -> int:
    suite = SystemQualification()
    report = suite.run_all()
    _print_console(report, suite._score)
    if report["status"] != "PASS":
        print("\nfailing details:")
        for k, v in suite._details.items():
            if not report["tests"][k]:
                print(f"  {k}: {v}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
