"""SCOS Stage 3.3 — Learning Pipeline Orchestrator (closed learning loop).

Closes the full self-learning loop by chaining ALREADY-CERTIFIED components through
their public APIs only:

    CSV
      -> Analytics Adapter        (load / validate / normalize)
      -> NormalizedAnalytics
      -> Analytics Translator     (scores + derived deltas)
      -> Feedback Engine          (scores -> style-update payload)
      -> Learning Coordinator     (governed apply via StyleMemory.update_style)
      -> Style Memory             (re-read the updated style)
      -> AssetBuilder v2          (regenerate on the new style)
      -> execution report

This module owns the WORKFLOW only. It implements no business logic, no learning
rules, and no conversion formulas — every decision lives inside the certified module
it delegates to. It never modifies a Certified Core; it only imports and coordinates.

Determinism: no RNG, no wall-clock except an injected clock. Identical inputs (fresh
state) produce an identical report, style version, asset bundle, and return value.
Every dependency is injectable.

Pure stdlib (+ the certified modules' own deps, e.g. numpy via AssetBuilder v2).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------- #
# import bootstrap — the certified modules use a mix of flat + package imports.
# The orchestrator is the top-level entry, so it wires their import paths itself
# (sys.path only; no Certified Core is modified).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATHS = (
    _REPO_ROOT,                                          # scos.* packages
    _REPO_ROOT / "scos" / "analytics" / "adapters",      # analytics_models, base_adapter
    _REPO_ROOT / "scos" / "analytics" / "translator",    # analytics_translator, rules
    _REPO_ROOT / "scos" / "analytics",                   # feedback_engine
    _REPO_ROOT / "scos" / "learning",                    # learning_coordinator, policy
)
for _p in _PATHS:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# Certified cores (public APIs only) -------------------------------------------
from base_adapter import AnalyticsValidationError          # noqa: E402
from analytics_translator import AnalyticsTranslator, TranslationError  # noqa: E402
from feedback_engine import FeedbackEngine                 # noqa: E402
from learning_coordinator import LearningCoordinator       # noqa: E402
from learning_policy import LearningPolicy                 # noqa: E402
from scos.assets.asset_builder import _derive_run_id        # noqa: E402  (run_id parity)
from scos.assets.asset_builder_v2 import AssetBuilderV2     # noqa: E402

# Pipeline-local model + helpers ------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))   # for `import pipeline_models`
from pipeline_models import (                               # noqa: E402
    PIPELINE_VERSION, REPORT_FILENAME, STATUS_SUCCESS, STATUS_FAILURE,
    PipelineError, decision_record, feedback_summary, learning_applied,
)

_DEFAULT_WORK_DIR = _REPO_ROOT / "scos" / "work" / "pipeline"


class LearningPipeline:
    """Deterministic orchestrator for the closed SCOS learning loop.

    All collaborators are injectable for testing; defaults wire the real certified
    components. ``execute`` runs the whole chain and returns the output contract.
    """

    def __init__(
        self,
        *,
        translator: AnalyticsTranslator | None = None,
        feedback_engine: FeedbackEngine | None = None,
        policy: LearningPolicy | None = None,
        coordinator_factory=None,
        asset_builder_factory=None,
        clock=None,
        work_dir: Path | str | None = None,
        learning_work_dir: Path | str | None = None,
    ) -> None:
        self.translator = translator or AnalyticsTranslator()
        self.feedback_engine = feedback_engine or FeedbackEngine()
        self.policy = policy or LearningPolicy()
        self._coordinator_factory = coordinator_factory
        self._asset_builder_factory = asset_builder_factory or (lambda eng: AssetBuilderV2(eng))
        self.clock = clock or (lambda: int(time.time()))
        self.work_dir = Path(work_dir) if work_dir is not None else _DEFAULT_WORK_DIR
        self.learning_work_dir = (
            Path(learning_work_dir) if learning_work_dir is not None
            else self.work_dir / "learning"
        )

    # ===================================================================== #
    # public API
    # ===================================================================== #
    def execute(self, analytics_csv, adapter, scene_plan, style_engine,
                content_type: str | None = None) -> dict:
        """Run the full learning loop. Always returns the output contract dict;
        never raises for an expected failure — failures return STATUS_FAILURE with
        deterministic, stage-tagged diagnostics."""
        ts = int(self.clock())
        run_id = _derive_run_id(scene_plan)
        report_path = self.work_dir / REPORT_FILENAME

        try:
            # 1-3. Load + validate + normalize analytics.
            records = self._load_normalize(analytics_csv, adapter)

            # 4. Translate normalized analytics -> scores + derived deltas.
            translator_payload = self._translate(records, content_type)
            resolved_ct = translator_payload["content_type"]

            # 5-6. Feedback evaluation -> the style-update payload.
            derived = self._feedback(translator_payload, resolved_ct)
            feedback = self._assemble_feedback(run_id, translator_payload, derived, resolved_ct)

            # 7. Governed learning via the coordinator (public API only).
            style_profile = self._resolve_style(style_engine, resolved_ct)
            coordinator = self._make_coordinator(style_engine)
            decision_out = self._coordinate(coordinator, feedback, style_profile)

            # 8. Re-read the (possibly) updated style.
            updated_style = style_engine.get_style(resolved_ct)

            # 9. Regenerate assets on the new style.
            asset_bundle = self._build_assets(style_engine, scene_plan, run_id)

        except PipelineError as exc:
            return self._fail(report_path, run_id, ts, exc, analytics_csv)

        # 10. Persist the report + return the success contract.
        decision = decision_out["decision"]
        style_version = decision_out["updated_style"]["style_version"]
        report = self._success_report(
            run_id, ts, analytics_csv, records, translator_payload, feedback,
            decision_out, updated_style, asset_bundle,
        )
        self._write_report(report_path, report)
        return {
            "status": STATUS_SUCCESS,
            "run_id": run_id,
            "learning_applied": learning_applied(decision),
            "decision": decision,
            "style_version": style_version,
            "asset_bundle": asset_bundle,
            "report_path": str(report_path),
            "timestamp": ts,
        }

    # ===================================================================== #
    # stages (each converts a domain failure into a PipelineError)
    # ===================================================================== #
    def _load_normalize(self, analytics_csv, adapter) -> list:
        try:
            adapter.load(analytics_csv)
        except Exception as exc:  # noqa: BLE001 — file/IO failure is a hard stop
            raise PipelineError("load", [str(exc)])

        errors = adapter.validate()
        if errors:
            raise PipelineError("validate", errors)

        try:
            records = adapter.normalize()
        except AnalyticsValidationError as exc:
            raise PipelineError("normalize", exc.errors)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("normalize", [str(exc)])

        if not records:
            raise PipelineError("normalize", ["no normalized records produced"])
        return records

    def _translate(self, records, content_type) -> dict:
        try:
            return self.translator.translate(records, content_type)
        except TranslationError as exc:
            raise PipelineError("translate", [str(exc)])
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("translate", [str(exc)])

    def _feedback(self, translator_payload, resolved_ct) -> dict:
        try:
            return self.feedback_engine.to_style_update(
                translator_payload, manifest={}, content_type=resolved_ct)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("feedback", [str(exc)])

    @staticmethod
    def _assemble_feedback(run_id, translator_payload, derived, resolved_ct) -> dict:
        """Build the exact dict the certified LearningCoordinator consumes.

        Scores come straight from the translator; ``derived_style_updates`` comes
        from the FeedbackEngine (the dedicated step 6 producer). ``run_id`` is
        injected so the coordinator's audit trail is traceable.
        """
        return {
            "run_id": run_id,
            "content_type": resolved_ct,
            "retention_score": translator_payload["retention_score"],
            "engagement_score": translator_payload["engagement_score"],
            "style_match_score": translator_payload["style_match_score"],
            "quality_score": translator_payload["quality_score"],
            "derived_style_updates": derived,
        }

    @staticmethod
    def _resolve_style(style_engine, resolved_ct) -> dict:
        style = style_engine.get_style(resolved_ct)
        stored_ids = {s["style_id"] for s in style_engine.list_styles()}
        if style["style_id"] not in stored_ids:
            raise PipelineError("style", [
                f"no persisted style for content_type {resolved_ct!r}: "
                f"cannot apply learning to a synthesized default"])
        return style

    def _make_coordinator(self, style_engine):
        if self._coordinator_factory is not None:
            return self._coordinator_factory(style_engine)
        return LearningCoordinator(
            style_engine, self.policy,
            now_fn=lambda: int(self.clock()),
            work_dir=self.learning_work_dir,
        )

    @staticmethod
    def _coordinate(coordinator, feedback, style_profile) -> dict:
        try:
            out = coordinator.coordinate({"feedback": feedback, "style_profile": style_profile})
        except Exception as exc:  # noqa: BLE001 — malformed payload -> hard stop
            raise PipelineError("coordinate", [str(exc)])
        # A REJECT caused by an unsafe/invalid derived payload is a hard stop
        # (data-integrity failure). A quality / "no actionable" REJECT is a valid
        # no-op outcome and is allowed to complete the loop.
        if out.get("decision") == "REJECT" and "unsafe" in (out.get("reason") or ""):
            raise PipelineError("coordinate",
                                [f"coordinator rejected invalid payload: {out.get('reason')}"])
        return out

    def _build_assets(self, style_engine, scene_plan, run_id) -> dict:
        try:
            return self._asset_builder_factory(style_engine).run(scene_plan, run_id)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("assets", [str(exc)])

    # ===================================================================== #
    # report assembly + atomic persistence
    # ===================================================================== #
    def _success_report(self, run_id, ts, analytics_csv, records, translator_payload,
                        feedback, decision_out, updated_style, asset_bundle) -> dict:
        return {
            "pipeline_version": PIPELINE_VERSION,
            "run_id": run_id,
            "status": STATUS_SUCCESS,
            "learning_applied": learning_applied(decision_out["decision"]),
            "input_analytics": self._input_summary(analytics_csv, len(records)),
            "translator_payload": translator_payload,
            "feedback_summary": feedback_summary(feedback),
            "coordinator_decision": decision_record(decision_out),
            "style_version": decision_out["updated_style"]["style_version"],
            "style_after": updated_style,
            "generated_assets": asset_bundle,
            "timestamp": ts,
        }

    def _fail(self, report_path, run_id, ts, exc: PipelineError, analytics_csv) -> dict:
        report = {
            "pipeline_version": PIPELINE_VERSION,
            "run_id": run_id,
            "status": STATUS_FAILURE,
            "learning_applied": False,
            "input_analytics": self._input_summary(analytics_csv, None),
            "error": {"stage": exc.stage, "errors": exc.errors},
            "timestamp": ts,
        }
        self._write_report(report_path, report)
        return {
            "status": STATUS_FAILURE,
            "run_id": run_id,
            "learning_applied": False,
            "decision": None,
            "style_version": None,
            "asset_bundle": None,
            "report_path": str(report_path),
            "timestamp": ts,
            "error": {"stage": exc.stage, "errors": exc.errors},
        }

    @staticmethod
    def _input_summary(analytics_csv, record_count) -> dict:
        """Content-addressed (path-free) input fingerprint for reproducibility."""
        try:
            digest = hashlib.sha256(Path(analytics_csv).read_bytes()).hexdigest()
        except OSError:
            digest = None
        return {"sha256": digest, "record_count": record_count}

    def _write_report(self, report_path: Path, report: dict) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = report_path.with_suffix(report_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False),
            encoding="utf-8")
        os.replace(tmp, report_path)  # atomic on same filesystem
