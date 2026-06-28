"""SCOS Stage 2.3 — Learning Coordinator (adaptive learning control layer).

The governance layer that closes the learning loop. It accepts FeedbackEngine output +
the current style profile, asks the (decoupled) LearningPolicy what to change, enforces
the policy's safety verdict, applies approved changes ONLY through
StyleMemoryEngine.update_style(), and maintains confidence, version history, an audit
trail, and rollback.

The Coordinator hard-codes NO policy rules — every threshold / clamp lives in
`learning_policy.py`. Local-first, stdlib only, fully deterministic (injected clock),
no RNG/ML/ffmpeg. It never modifies StyleMemoryEngine's implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from scos.memory.style_memory import StyleMemoryEngine
from learning_policy import LearningPolicy

# Repo root: scos/learning/learning_coordinator.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORK_DIR = _REPO_ROOT / "scos" / "work" / "learning"

CONFIDENCE_STEP = 0.05          # governance constant (not a policy rule)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class LearningCoordinator:
    """Deterministic governance engine; delegates all rules to LearningPolicy."""

    def __init__(self, style_engine: StyleMemoryEngine, policy: LearningPolicy | None = None,
                 now_fn=None, work_dir: Path | str = _WORK_DIR) -> None:
        self.engine = style_engine
        self.policy = policy or LearningPolicy()
        self.now_fn = now_fn or (lambda: int(time.time()))
        self.work_dir = Path(work_dir)
        self.audit_path = self.work_dir / "learning_audit.json"
        self.state_path = self.work_dir / "learning_state.json"
        self.history_path = self.work_dir / "style_history.json"

    # ===================================================================== #
    # public API
    # ===================================================================== #
    def coordinate(self, payload: dict) -> dict:
        feedback = payload["feedback"]
        style = dict(payload["style_profile"])
        style_id = style["style_id"]
        ts = self.now_fn()
        before = dict(style)

        # 1. Ask the policy what to do.
        decision = self.policy.evaluate(style, feedback)
        if decision["action"] == "reject":
            delta = -CONFIDENCE_STEP if decision["penalize"] else 0.0
            return self._finalize("REJECT", decision["reason"], style_id, before, before,
                                  feedback, ts, confidence_delta=delta)

        # 2. Enforce the policy's safety verdict.
        safety = self.policy.enforce_safety(decision["proposed"])
        if not safety["valid"]:
            return self._finalize("REJECT", f"unsafe value: {safety['reason']}", style_id,
                                  before, before, feedback, ts, confidence_delta=-CONFIDENCE_STEP)

        proposed = safety["proposed"]
        verdict = "CLAMP" if safety["clamped"] else "APPLY"
        reason = ("clamped " + ",".join(safety["clamped"])) if safety["clamped"] else "policy applied"

        # 3. Apply via the public API only.
        self.engine.update_style(style_id, proposed)
        after = dict(before); after.update(proposed)

        return self._finalize(verdict, reason, style_id, before, after, feedback, ts,
                              confidence_delta=+CONFIDENCE_STEP, version_bump=True)

    def rollback(self, style_id: str, version: int) -> dict:
        history = self._load_json(self.history_path, {})
        snaps = history.get(style_id)
        if not snaps:
            raise ValueError(f"no version history for style_id {style_id!r}")
        match = next((s for s in snaps if s["version"] == version), None)
        if match is None:
            raise ValueError(f"version {version} not found for style_id {style_id!r}")

        snapshot = match["profile"]
        before = self._current_profile(style_id) or snapshot
        restore = {k: snapshot[k] for k in ("avg_color_palette", "audio_frequency_bias",
                                            "scene_pacing_profile") if k in snapshot}
        self.engine.update_style(style_id, restore)

        ts = self.now_fn()
        state = self._load_state()
        state["versions"][style_id] = version
        self._save_state(state)

        after = dict(before); after.update(restore)
        audit_id = self._audit_id("rollback", style_id, version, before, after)
        self._append_audit({
            "audit_id": audit_id, "decision": "ROLLBACK",
            "reason": f"restored version {version}",
            "style_before": before, "style_after": after,
            "feedback_summary": {}, "timestamp": ts,
        })
        return {"decision": "ROLLBACK", "reason": f"restored version {version}",
                "updated_style": {**after, "style_version": version},
                "audit_id": audit_id, "timestamp": ts}

    # ===================================================================== #
    # finalize: confidence + version + audit + output
    # ===================================================================== #
    def _finalize(self, decision: str, reason: str, style_id: str, before: dict,
                  after: dict, feedback: dict, ts: int, confidence_delta: float,
                  version_bump: bool = False) -> dict:
        state = self._load_state()
        state["confidence"] = round(_clamp(state["confidence"] + confidence_delta, 0.0, 1.0), 6)

        version = state["versions"].get(style_id, 0)
        if version_bump:
            if not self._has_history(style_id):
                self._snapshot(style_id, 0, before, "seed", ts)   # seed v0 = before
            version += 1
            state["versions"][style_id] = version

        audit_id = self._audit_id(decision, style_id, version, before, after)
        if version_bump:
            self._snapshot(style_id, version, after, audit_id, ts)
        self._save_state(state)

        self._append_audit({
            "audit_id": audit_id, "decision": decision, "reason": reason,
            "style_before": before, "style_after": after,
            "feedback_summary": self._feedback_summary(feedback), "timestamp": ts,
        })
        return {"decision": decision, "reason": reason,
                "updated_style": {**after, "style_version": version},
                "audit_id": audit_id, "timestamp": ts}

    @staticmethod
    def _feedback_summary(feedback: dict) -> dict:
        return {k: feedback.get(k) for k in (
            "run_id", "retention_score", "engagement_score",
            "style_match_score", "quality_score")}

    def _audit_id(self, decision: str, style_id: str, version: int,
                  before: dict, after: dict) -> str:
        blob = "|".join([decision, style_id, str(version), _canon(before), _canon(after)])
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ===================================================================== #
    # version history
    # ===================================================================== #
    def _has_history(self, style_id: str) -> bool:
        return bool(self._load_json(self.history_path, {}).get(style_id))

    def _snapshot(self, style_id: str, version: int, profile: dict,
                  audit_id: str, ts: int) -> None:
        history = self._load_json(self.history_path, {})
        snaps = history.setdefault(style_id, [])
        if any(s["version"] == version for s in snaps):
            return
        snaps.append({"version": version, "profile": dict(profile),
                      "audit_id": audit_id, "timestamp": ts})
        snaps.sort(key=lambda s: s["version"])
        self._save_json(self.history_path, history)

    def _current_profile(self, style_id: str) -> dict | None:
        for s in self.engine.list_styles():
            if s["style_id"] == style_id:
                return s
        return None

    # ===================================================================== #
    # persistence (atomic, deterministic)
    # ===================================================================== #
    def _load_state(self) -> dict:
        st = self._load_json(self.state_path, None)
        if not isinstance(st, dict):
            st = {}
        st.setdefault("confidence", 0.5)
        st.setdefault("versions", {})
        return st

    def _save_state(self, state: dict) -> None:
        self._save_json(self.state_path, state)

    def _append_audit(self, entry: dict) -> None:
        log = self._load_json(self.audit_path, [])
        if not isinstance(log, list):
            log = []
        if any(e.get("audit_id") == entry["audit_id"] for e in log):
            return                                  # no duplicates
        log.append(entry)
        self._save_json(self.audit_path, log)

    @staticmethod
    def _load_json(path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _save_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)
