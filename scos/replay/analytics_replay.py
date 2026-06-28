"""SCOS Stage 3.4 — Analytics Replay Engine (deterministic historical re-run).

Replays MANY historical analytics records (one CSV, many CSVs, or in-memory
records) through the already-certified chain — used through public APIs only:

    Adapter -> Translator -> FeedbackEngine -> LearningCoordinator -> StyleMemory
    -> (optionally) AssetBuilder v2 -> one combined replay report

This module owns the WORKFLOW only. It implements no learning rules and no
conversion formulas — every decision lives inside the certified module it
delegates to. It never modifies a Certified Core; it only imports/coordinates.

Failure policy (the key difference from Stage 3.3's LearningPipeline): one bad
record must NOT abort the whole replay. Only 3 truly fatal conditions abort
everything (unreadable dataset file, broken adapter wiring, report-store write
failure) — raised as ReplayFatalError. Every other problem becomes a per-record
FAIL result and replay continues.

Determinism: no RNG, no wall-clock (now_fn defaults to a fixed clock), no
threading/multiprocessing/async/network. Every collaborator is injectable.

Pure stdlib (+ the certified modules' own deps, e.g. numpy via AssetBuilder v2).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# import bootstrap — the certified modules use a mix of flat + package imports.
# The replay engine is a top-level entry point, so it wires their import paths
# itself (sys.path only; no Certified Core is modified).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATHS = (
    _REPO_ROOT,                                          # scos.* packages
    _REPO_ROOT / "scos" / "analytics" / "adapters",      # base_adapter (AnalyticsValidationError)
    _REPO_ROOT / "scos" / "analytics" / "translator",    # analytics_translator (TranslationError)
)
for _p in _PATHS:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from base_adapter import AnalyticsValidationError          # noqa: E402
from analytics_translator import TranslationError           # noqa: E402
from scos.assets.asset_builder import _derive_run_id        # noqa: E402  (run_id parity)

# Replay-local model + helpers ---------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))   # for `import replay_models`
from replay_models import (                                  # noqa: E402
    REPORT_FILENAME, STATUS_PASS,
    DECISION_APPLY, DECISION_CLAMP, DECISION_REJECT, DECISION_FAIL,
    ReplayFatalError, result_record, report,
)

_DEFAULT_WORK_DIR = _REPO_ROOT / "scos" / "work" / "replay"
_UNSAFE_PREFIX = "unsafe value: "


def _safe_token(value: str) -> str:
    """Filesystem/identifier-safe slice of an arbitrary record id."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value))[:64]


class _FileOutcome:
    """Internal: the result of attempting to load+normalize one CSV file."""

    __slots__ = ("records", "file_errors")

    def __init__(self, records: list | None, file_errors: list[str] | None) -> None:
        self.records = records
        self.file_errors = file_errors


class _Accumulator:
    """Tracks running totals + result entries across one replay call."""

    def __init__(self) -> None:
        self.processed = 0
        self.applied = 0
        self.rejected = 0
        self.results: list[dict] = []
        self._updated_style_ids: set[str] = set()

    def add(self, entry: dict) -> None:
        self.processed += 1
        self.results.append(entry)
        decision = entry["decision"]
        if decision in (DECISION_APPLY, DECISION_CLAMP):
            self.applied += 1
            if entry.get("style_id"):
                self._updated_style_ids.add(entry["style_id"])
        elif decision == DECISION_REJECT:
            self.rejected += 1

    @property
    def styles_updated(self) -> int:
        return len(self._updated_style_ids)


class AnalyticsReplayEngine:
    """Deterministic orchestrator that replays historical analytics through the
    certified learning chain. All major collaborators are injected as
    already-constructed instances — ``coordinator`` is expected to already be
    bound to its own style engine (reachable as ``coordinator.engine``).

    ``asset_builder_factory``, if given, is a ZERO-ARG callable (deliberately
    different from Stage 3.3's ``factory(engine)`` — the coordinator here
    already owns its style engine, so the factory needs nothing from the
    caller). Asset regeneration requires a constructor-time ``scene_plan``.
    """

    def __init__(
        self,
        adapter,
        translator,
        feedback_engine,
        coordinator,
        asset_builder_factory=None,
        scene_plan: dict | None = None,
        now_fn=lambda: 0,
        work_dir: Path | str | None = None,
        session_id: str | None = None,
    ) -> None:
        if asset_builder_factory is not None and scene_plan is None:
            raise ValueError("asset_builder_factory requires scene_plan")
        self.adapter = adapter
        self.translator = translator
        self.feedback_engine = feedback_engine
        self.coordinator = coordinator
        self.asset_builder_factory = asset_builder_factory
        self.scene_plan = scene_plan
        self.now_fn = now_fn
        self.work_dir = Path(work_dir) if work_dir is not None else _DEFAULT_WORK_DIR
        self.session_id = session_id
        self._base_run_id = _derive_run_id(scene_plan) if scene_plan is not None else None

    # ===================================================================== #
    # public API — replay(), replay_records(), replay_history() share the
    # exact same per-record path (_process_one) and report assembly.
    # ===================================================================== #
    def replay(self, csv_file, *, on_progress=None) -> dict:
        data_bytes = self._read_bytes_or_fatal(csv_file)
        session_id = self._resolve_session_id(data_bytes)
        acc = _Accumulator()
        outcome = self._load_one(csv_file)
        self._consume_file_outcome(outcome, csv_file, session_id, acc, on_progress)
        return self._finalize(acc, session_id)

    def replay_history(self, csv_files, *, on_progress=None) -> dict:
        csv_files = list(csv_files)
        combined = bytearray()
        for f in csv_files:
            combined += self._read_bytes_or_fatal(f)
        session_id = self._resolve_session_id(bytes(combined))
        acc = _Accumulator()
        for f in csv_files:
            outcome = self._load_one(f)
            self._consume_file_outcome(outcome, f, session_id, acc, on_progress)
        return self._finalize(acc, session_id)

    def replay_records(self, records, *, on_progress=None) -> dict:
        records = list(records)
        session_id = self._resolve_session_id(self._canon_records(records))
        acc = _Accumulator()
        total = len(records)
        for i, record in enumerate(records):
            entry = self._process_one(record, session_id)
            acc.add(entry)
            if on_progress is not None:
                on_progress(i + 1, total, entry["record_id"])
        return self._finalize(acc, session_id)

    # ===================================================================== #
    # file loading (fatal vs per-file FAIL)
    # ===================================================================== #
    @staticmethod
    def _read_bytes_or_fatal(csv_file) -> bytes:
        try:
            return Path(csv_file).read_bytes()
        except OSError as exc:
            raise ReplayFatalError("load", [str(exc)])

    def _load_one(self, csv_file) -> _FileOutcome:
        try:
            self.adapter.load(csv_file)
        except Exception as exc:  # noqa: BLE001 — unreadable/wiring failure is fatal
            raise ReplayFatalError("load", [str(exc)])

        errors = self.adapter.validate()
        if errors:
            return _FileOutcome(records=None, file_errors=errors)

        try:
            records = self.adapter.normalize()
        except AnalyticsValidationError as exc:
            return _FileOutcome(records=None, file_errors=exc.errors)
        except Exception as exc:  # noqa: BLE001
            return _FileOutcome(records=None, file_errors=[str(exc)])

        if not records:
            return _FileOutcome(records=None, file_errors=["no normalized records produced"])
        return _FileOutcome(records=records, file_errors=None)

    def _consume_file_outcome(self, outcome: _FileOutcome, csv_file, session_id: str,
                              acc: _Accumulator, on_progress) -> None:
        if outcome.file_errors is not None:
            entry = result_record(
                record_id=str(csv_file), decision=DECISION_FAIL,
                timestamp=int(self.now_fn()), error="; ".join(outcome.file_errors),
                session_id=session_id,
            )
            acc.add(entry)
            if on_progress is not None:
                on_progress(acc.processed, acc.processed, entry["record_id"])
            return

        total = len(outcome.records)
        for i, record in enumerate(outcome.records):
            entry = self._process_one(record, session_id)
            acc.add(entry)
            if on_progress is not None:
                on_progress(i + 1, total, entry["record_id"])

    # ===================================================================== #
    # per-record processing — never raises out of this method.
    # ===================================================================== #
    def _process_one(self, record, session_id: str) -> dict:
        record_id = self._record_id(record)
        ts = int(self.now_fn())

        try:
            payload = self.translator.translate([record])
        except TranslationError as exc:
            return result_record(record_id, DECISION_FAIL, timestamp=ts,
                                 error=str(exc), session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            return result_record(record_id, DECISION_FAIL, timestamp=ts,
                                 error=str(exc), session_id=session_id)

        content_type = payload["content_type"]
        quality_score = payload.get("quality_score")

        try:
            style_engine = self.coordinator.engine
            style = style_engine.get_style(content_type)
            style_id = style["style_id"]
            stored_ids = {s["style_id"] for s in style_engine.list_styles()}
            if style_id not in stored_ids:
                return result_record(
                    record_id, DECISION_FAIL, style_id=style_id, quality_score=quality_score,
                    timestamp=ts, session_id=session_id,
                    error=f"no persisted style for content_type {content_type!r}: "
                          f"cannot apply learning to a synthesized default",
                )
        except Exception as exc:  # noqa: BLE001
            return result_record(record_id, DECISION_FAIL, quality_score=quality_score,
                                 timestamp=ts, error=str(exc), session_id=session_id)

        run_id = self._make_run_id(session_id, record_id)

        try:
            feedback = self.feedback_engine.to_style_update(
                payload, manifest={}, content_type=content_type)
        except Exception as exc:  # noqa: BLE001
            return result_record(record_id, DECISION_FAIL, style_id=style_id,
                                 quality_score=quality_score, run_id=run_id, timestamp=ts,
                                 error=str(exc), session_id=session_id)

        coord_feedback = {
            "run_id": run_id,
            "content_type": content_type,
            "retention_score": payload["retention_score"],
            "engagement_score": payload["engagement_score"],
            "style_match_score": payload["style_match_score"],
            "quality_score": payload["quality_score"],
            "derived_style_updates": feedback,
        }
        try:
            out = self.coordinator.coordinate(
                {"feedback": coord_feedback, "style_profile": style})
        except Exception as exc:  # noqa: BLE001
            return result_record(record_id, DECISION_FAIL, style_id=style_id,
                                 quality_score=quality_score, run_id=run_id, timestamp=ts,
                                 error=str(exc), session_id=session_id)

        decision = out.get("decision")
        reason = out.get("reason") or ""
        if decision == DECISION_REJECT and reason.startswith(_UNSAFE_PREFIX):
            return result_record(record_id, DECISION_FAIL, style_id=style_id,
                                 quality_score=quality_score, run_id=run_id, timestamp=ts,
                                 error=f"coordinator rejected invalid payload: {reason}",
                                 session_id=session_id)

        asset_hash = None
        if decision in (DECISION_APPLY, DECISION_CLAMP) and self.asset_builder_factory is not None:
            try:
                bundle = self.asset_builder_factory().run(self.scene_plan, run_id)
                asset_hash = self._hash_asset_bundle(bundle)
            except Exception as exc:  # noqa: BLE001
                return result_record(record_id, DECISION_FAIL, style_id=style_id,
                                     quality_score=quality_score, run_id=run_id, timestamp=ts,
                                     error=f"asset regeneration failed: {exc}",
                                     session_id=session_id)

        return result_record(
            record_id, decision, style_id=style_id, quality_score=quality_score,
            run_id=run_id, asset_hash=asset_hash, timestamp=ts, session_id=session_id,
        )

    @staticmethod
    def _record_id(record) -> str:
        return str(getattr(record, "video_id", None) or id(record))

    def _make_run_id(self, session_id: str, record_id: str) -> str:
        base = self._base_run_id or "norun"
        return f"{session_id}_{base}_{_safe_token(record_id)}"

    # ===================================================================== #
    # session id resolution + asset hashing
    # ===================================================================== #
    def _resolve_session_id(self, data: bytes) -> str:
        if self.session_id is not None:
            return self.session_id
        return "replay_" + hashlib.sha256(data).hexdigest()[:16]

    @staticmethod
    def _canon_records(records: list) -> bytes:
        blob = json.dumps([r.to_dict() for r in records], sort_keys=True, ensure_ascii=False)
        return blob.encode("utf-8")

    @staticmethod
    def _hash_asset_bundle(bundle: dict) -> str:
        h = hashlib.sha256()
        manifest_path = _REPO_ROOT / bundle["manifest_path"]
        h.update(manifest_path.read_bytes())
        for asset in sorted(bundle["assets"], key=lambda a: a["scene_id"]):
            h.update((_REPO_ROOT / asset["image_path"]).read_bytes())
            h.update((_REPO_ROOT / asset["audio_path"]).read_bytes())
        return h.hexdigest()

    # ===================================================================== #
    # report assembly + atomic persistence
    # ===================================================================== #
    def _finalize(self, acc: _Accumulator, session_id: str) -> dict:
        out = report(
            STATUS_PASS, acc.processed, acc.applied, acc.rejected,
            acc.styles_updated, acc.results, session_id,
        )
        self._write_report(out)
        return out

    def _write_report(self, out: dict) -> None:
        report_path = self.work_dir / REPORT_FILENAME
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = report_path.with_suffix(report_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(out, sort_keys=True, indent=2, ensure_ascii=False),
                encoding="utf-8")
            os.replace(tmp, report_path)  # atomic on same filesystem
        except OSError as exc:
            raise ReplayFatalError("report", [str(exc)])
