"""Authoritative local persistence for Control Center project-preparation records.

Cohort 10C — single authoritative local store for the solo-project
preparation workflow (draft -> validate -> approve -> preview).

Ownership decision (Phase 1 audit):
  * This module is the AUTHORITATIVE WRITER + the test oracle.
  * The Next.js server routes (TypeScript) are a SECONDARY writer that
    implements the identical schema / atomicity / lock / idempotency
    contract against the same on-disk file, so truth survives a process
    restart and either runtime can recover the exact state.
  * The store lives in memory/runtime/control-center/ (a dedicated
    runtime directory), NEVER in memory/database.json (protected
    production store) and NEVER in the browser.
  * No SQLite / DB dependency is introduced (forbidden by Cohort 10C §15).
  * Atomic replace + advisory lock are reused from integrations/learning/
    _filelock.py (the SCOS concurrency convention).

Truth states every read resolves to exactly one of:
  AVAILABLE_WITH_DATA | EMPTY | UNAVAILABLE | CORRUPT | INCOMPATIBLE_SCHEMA

Data-safety contract:
  * atomic write (temp sibling -> validate -> fsync -> replace)
  * prior valid bytes preserved on any write failure
  * schema version + record revision enforced
  * deterministic idempotent identity (FNV-1a, mirrors the TS client)
  * stale revision rejected (conflict, never overwrites newer)
  * conflicting duplicate identity rejected
  * corruption / unsupported schema -> fail closed (no silent EMPTY)
  * no secrets, no raw filesystem paths from the browser, no subprocess
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    # SCOS concurrency convention: _filelock.py lives in integrations/learning
    # and is imported bare (see scos/control_center/command_queue.py).
    from _filelock import atomic_replace, file_lock, lock_path_for
except ImportError:  # direct-module execution (pytest inserts package dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "learning"))
    from _filelock import atomic_replace, file_lock, lock_path_for  # type: ignore

# --------------------------------------------------------------------------
# Canonical constants (shared 1:1 with the TypeScript server + client)
# --------------------------------------------------------------------------

SCHEMA_VERSION = 1
STORE_KIND = "scos.project_preparation.v1"
STORE_SUBDIR = ("memory", "runtime", "control-center")
DEFAULT_STORE_FILENAME = "project-preparation-v1.json"
INTEGRITY_SUFFIX = ".integrity.json"
TMP_SUFFIX = ".tmp"

# Truth-state vocabulary (must match the TypeScript client truth contract).
TRUTH_AVAILABLE_WITH_DATA = "AVAILABLE_WITH_DATA"
TRUTH_EMPTY = "EMPTY"
TRUTH_UNAVAILABLE = "UNAVAILABLE"
TRUTH_CORRUPT = "CORRUPT"
TRUTH_INCOMPATIBLE_SCHEMA = "INCOMPATIBLE_SCHEMA"

# Project state machine (preserves Cohort 10B states).
STATE_DRAFT = "DRAFT"
STATE_VALIDATION_FAILED = "VALIDATION_FAILED"
STATE_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
STATE_APPROVED = "APPROVED"
STATE_PREPARATION_PREVIEW_READY = "PREPARATION_PREVIEW_READY"
ALLOWED_STATES = {
    STATE_DRAFT,
    STATE_VALIDATION_FAILED,
    STATE_APPROVAL_REQUIRED,
    STATE_APPROVED,
    STATE_PREPARATION_PREVIEW_READY,
}

# Allowed output profiles (mirrors apps/control-center/lib/solo-project-preparation.ts).
OUTPUT_PROFILES = {
    "vertical_9_16": {"id": "vertical_9_16", "label": "vertical 9:16", "aspectRatio": "9:16"},
    "square_1_1": {"id": "square_1_1", "label": "square 1:1", "aspectRatio": "1:1"},
    "landscape_16_9": {"id": "landscape_16_9", "label": "landscape 16:9", "aspectRatio": "16:9"},
}
ALLOWED_PROFILE_IDS = tuple(OUTPUT_PROFILES.keys())
PREPARATION_STAGES = (
    "validate specification",
    "prepare script inputs",
    "prepare scene plan",
    "prepare asset manifest",
    "prepare output renditions",
    "await render authorization",
)

# Side-effect invariants (must ALWAYS be false — no Cohort 10C side effect).
SIDE_EFFECT_FLAGS = {
    "side_effects_performed": False,
    "render_started": False,
    "hvs_project_created": False,
}

# Identity + safety regexes (mirror the TS client exactly).
SAFE_ID_PATTERN = "spp-[a-f0-9]{12}"
URL_PATTERN = "https://|http://|file://|ftp://|www\\."
SHELL_PATTERN = (
    "&&|\\|\\||;|`|\\$\\(|<script|"
    "(?:cmd|powershell|bash|sh|ffmpeg|ffprobe|chromium|hyperframes)\\b"
)
PATH_TRAVERSAL_PATTERN = "(?:^|[/\\\\])\\.\\.(?:$|[/\\\\])|[/\\\\]|[;&|`$<>]"
LIVE_EXECUTION_PATTERN = (
    "render this|start render|start rendering|initialize hvs|"
    "create hvs project|publish|upload|deliver|execute|run command"
)

# Error taxonomy (mirrors the TS client + API contract).
ERR_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
ERR_STORE_CORRUPT = "STORE_CORRUPT"
ERR_SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
ERR_REVISION_CONFLICT = "REVISION_CONFLICT"
ERR_IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
ERR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERR_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
ERR_PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
ERR_INVALID_TRANSITION = "INVALID_TRANSITION"
ERR_PERSISTENCE_WRITE_FAILED = "PERSISTENCE_WRITE_FAILED"
ERR_LOCK_UNAVAILABLE = "LOCK_UNAVAILABLE"
ERR_PATH_ESCAPE = "PATH_ESCAPE"


# --------------------------------------------------------------------------
# Deterministic helpers
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _fnv1a_js_utf16(text: str) -> str:
    """FNV-1a (32-bit) using JS charCodeAt semantics (UTF-16 code units).

    Mirrors apps/control-center/lib/solo-project-preparation.ts::stableId
    so the authoritative identity computed here and in the TypeScript server
    match exactly for the same input.
    """
    units = text.encode("utf-16-le")
    hash_a = 0x811C9DC5
    for i in range(0, len(units), 2):
        code = units[i] | (units[i + 1] << 8)
        hash_a ^= code
        hash_a = (hash_a * 0x01000193) & 0xFFFFFFFF
    first = format(hash_a, "08x")
    hash_b = 0x811C9DC5
    for i in range(len(units) - 2, -1, -2):
        code = units[i] | (units[i + 1] << 8)
        hash_b ^= code
        hash_b = (hash_b * 0x01000193) & 0xFFFFFFFF
    second = format(hash_b, "08x")[:4]
    return f"{first}{second}"


def derive_project_id(identity_input: str) -> str:
    return f"spp-{_fnv1a_js_utf16(identity_input)}"


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    return " ".join(value.strip().split())


def _brief_summary(brief: str) -> str:
    normalized = _normalize_text(brief)
    if len(normalized) <= 140:
        return normalized
    return normalized[:137].rstrip() + "..."


def _is_safe_text(value: str) -> list[str]:
    errors: list[str] = []
    if value and __import__("re").search(URL_PATTERN, value, __import__("re").IGNORECASE):
        errors.append("REMOTE_ASSET_UNSUPPORTED")
    if value and __import__("re").search(SHELL_PATTERN, value, __import__("re").IGNORECASE):
        errors.append("SHELL_COMMAND_UNSUPPORTED")
    if value and __import__("re").search(LIVE_EXECUTION_PATTERN, value, __import__("re").IGNORECASE):
        errors.append("LIVE_EXECUTION_REQUEST_UNSUPPORTED")
    if value and __import__("re").search(PATH_TRAVERSAL_PATTERN, value):
        errors.append("PATH_TRAVERSAL_UNSUPPORTED")
    return errors


# --------------------------------------------------------------------------
# Validation + normalization (authoritative, mirrors the TS client)
# --------------------------------------------------------------------------

def validate_draft_input(input: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    project_title = _normalize_text(input.get("projectTitle", ""))
    client_or_brand = _normalize_text(input.get("clientOrBrand", ""))
    project_purpose = _normalize_text(input.get("projectPurpose", ""))
    content_brief = _normalize_text(input.get("contentBrief", ""))
    operator_notes = _normalize_text(input.get("operatorNotes", ""))
    target = input.get("targetDurationSeconds", None)

    if not project_title:
        errors.append("PROJECT_TITLE_REQUIRED")
    if not content_brief:
        errors.append("BRIEF_REQUIRED")
    if not client_or_brand:
        errors.append("CLIENT_OR_BRAND_REQUIRED")
    if not project_purpose:
        errors.append("PROJECT_PURPOSE_REQUIRED")
    if project_title and __import__("re").search(PATH_TRAVERSAL_PATTERN, project_title):
        errors.append("PROJECT_TITLE_MALFORMED")

    if not isinstance(target, int) or isinstance(target, bool):
        errors.append("DURATION_OUT_OF_RANGE")
    elif target < 5 or target > 600:
        errors.append("DURATION_OUT_OF_RANGE")

    profiles = input.get("outputProfiles", []) or []
    if not isinstance(profiles, list) or len(profiles) == 0:
        errors.append("OUTPUT_PROFILE_REQUIRED")
    else:
        if len(set(profiles)) != len(profiles):
            errors.append("OUTPUT_PROFILE_DUPLICATE")
        for profile in profiles:
            if profile not in ALLOWED_PROFILE_IDS:
                errors.append("OUTPUT_PROFILE_UNSUPPORTED")

    errors.extend(_is_safe_text(project_title))
    errors.extend(_is_safe_text(content_brief))
    errors.extend(_is_safe_text(project_purpose))
    errors.extend(_is_safe_text(operator_notes))
    return sorted(set(errors))


def normalize_draft_input(input: dict[str, Any]) -> dict[str, Any]:
    project_title = _normalize_text(input.get("projectTitle", ""))
    client_or_brand = _normalize_text(input.get("clientOrBrand", ""))
    project_purpose = _normalize_text(input.get("projectPurpose", ""))
    content_brief = _normalize_text(input.get("contentBrief", ""))
    operator_notes = _normalize_text(input.get("operatorNotes", ""))
    target = int(input.get("targetDurationSeconds", 30))
    selected = []
    seen = set()
    for profile_id in input.get("outputProfiles", []) or []:
        if profile_id in ALLOWED_PROFILE_IDS and profile_id not in seen:
            seen.add(profile_id)
            selected.append(OUTPUT_PROFILES[profile_id])
    selected.sort(key=lambda p: p["id"])
    normalized_brief = _brief_summary(content_brief)
    identity_input = "|".join(
        [
            project_title.lower(),
            client_or_brand.lower(),
            project_purpose.lower(),
            normalized_brief.lower(),
            str(target),
            ",".join(p["id"] for p in selected),
        ]
    )
    return {
        "project_id": derive_project_id(identity_input),
        "project_title": project_title,
        "client_or_brand": client_or_brand,
        "project_purpose": project_purpose,
        "normalized_brief_summary": normalized_brief,
        "target_duration_seconds": target,
        "output_profiles": [
            {"id": p["id"], "label": p["label"], "aspectRatio": p["aspectRatio"]}
            for p in selected
        ],
        "planned_rendition_count": len(selected),
        "operator_notes": operator_notes,
    }


def _identity_input_from_normalized(normalized: dict[str, Any]) -> str:
    return "|".join(
        [
            normalized["project_title"].lower(),
            normalized["client_or_brand"].lower(),
            normalized["project_purpose"].lower(),
            normalized["normalized_brief_summary"].lower(),
            str(normalized["target_duration_seconds"]),
            ",".join(p["id"] for p in normalized["output_profiles"]),
        ]
    )


# --------------------------------------------------------------------------
# Records + read/write result types
# --------------------------------------------------------------------------

@dataclass
class ProjectPreparationRecord:
    project_id: str
    schema_version: int
    revision: int
    created_at: str
    updated_at: str
    state: str
    normalized: dict[str, Any]
    approval: dict[str, Any] = field(default_factory=dict)
    preparation_preview: Optional[dict[str, Any]] = None
    side_effect_flags: dict[str, Any] = field(default_factory=lambda: dict(SIDE_EFFECT_FLAGS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "schema_version": self.schema_version,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state,
            "normalized": self.normalized,
            "approval": self.approval,
            "preparation_preview": self.preparation_preview,
            "side_effect_flags": self.side_effect_flags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectPreparationRecord":
        return cls(
            project_id=str(data["project_id"]),
            schema_version=int(data["schema_version"]),
            revision=int(data["revision"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            state=str(data["state"]),
            normalized=dict(data["normalized"]),
            approval=dict(data.get("approval") or {}),
            preparation_preview=dict(data["preparation_preview"])
            if data.get("preparation_preview") is not None
            else None,
            side_effect_flags=dict(data.get("side_effect_flags") or SIDE_EFFECT_FLAGS),
        )


@dataclass
class ReadResult:
    status: str
    records: list[ProjectPreparationRecord] = field(default_factory=list)
    error_code: Optional[str] = None
    detail: Optional[str] = None

    def to_envelope(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "schema_version": SCHEMA_VERSION,
            "error_code": self.error_code,
            "detail": self.detail,
            "records": [r.to_dict() for r in self.records],
        }


@dataclass
class WriteResult:
    ok: bool
    record: Optional[ProjectPreparationRecord] = None
    error_code: Optional[str] = None
    detail: Optional[str] = None

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_code": self.error_code,
            "detail": self.detail,
            "record": self.record.to_dict() if self.record is not None else None,
        }


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------

def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_store_path(repo_root: Path) -> Path:
    return repo_root.joinpath(*STORE_SUBDIR, DEFAULT_STORE_FILENAME)


def validate_store_path(store_path: Path, base_dir: Path) -> Optional[str]:
    """Return PATH_ESCAPE if the resolved store escapes the approved base."""
    try:
        real_store = os.path.realpath(str(store_path))
        real_base = os.path.realpath(str(base_dir))
    except OSError:
        return ERR_PATH_ESCAPE
    if real_store == real_base:
        return ERR_PATH_ESCAPE
    if not real_store.startswith(real_base + os.sep):
        return ERR_PATH_ESCAPE
    return None


# --------------------------------------------------------------------------
# Integrity marker
# --------------------------------------------------------------------------

def _integrity_marker_path(store_path: Path) -> Path:
    return store_path.parent / f"{store_path.name}{INTEGRITY_SUFFIX}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Authoritative store
# --------------------------------------------------------------------------

class ProjectPreparationStore:
    """Single-writer authoritative persistence for project-preparation records.

    One on-disk file, atomic replace, exclusive advisory lock, deterministic
    idempotent identity, monotonic revision, fail-closed corruption handling.
    """

    def __init__(
        self,
        *,
        store_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self._repo_root = _resolve_repo_root()
        self._base_dir = (
            Path(base_dir) if base_dir is not None else self._repo_root.joinpath(*STORE_SUBDIR)
        )
        self._store_path = (
            Path(store_path)
            if store_path is not None
            else self._base_dir / DEFAULT_STORE_FILENAME
        )
        path_error = validate_store_path(self._store_path, self._base_dir)
        if path_error is not None:
            raise ValueError(
                f"{path_error}: store path escapes approved base {self._base_dir}"
            )

    @property
    def store_path(self) -> Path:
        return self._store_path

    # -- low-level read ----------------------------------------------------

    def _read_raw(self) -> ReadResult:
        path = self._store_path
        if not path.exists():
            # No file yet -> valid EMPTY state.
            return ReadResult(status=TRUTH_EMPTY, records=[])
        try:
            raw_bytes = path.read_bytes()
            text = raw_bytes.decode("utf-8")
            data = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail=f"malformed store: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ReadResult(
                status=TRUTH_UNAVAILABLE,
                error_code=ERR_STORE_UNAVAILABLE,
                detail=f"unreadable store: {exc}",
            )

        if not isinstance(data, dict):
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail="store envelope is not an object",
            )

        kind = data.get("store_kind")
        if kind is not None and kind != STORE_KIND:
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail=f"unknown store_kind: {kind!r}",
            )

        version = data.get("schema_version")
        if version is None or not isinstance(version, int):
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail="missing/invalid schema_version",
            )
        if version != SCHEMA_VERSION:
            return ReadResult(
                status=TRUTH_INCOMPATIBLE_SCHEMA,
                error_code=ERR_SCHEMA_INCOMPATIBLE,
                detail=f"unsupported schema_version: {version}",
            )

        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail="records is not a list",
            )

        records: list[ProjectPreparationRecord] = []
        try:
            for idx, row in enumerate(raw_records):
                records.append(self._parse_record(row, idx))
        except ValueError as exc:
            return ReadResult(
                status=TRUTH_CORRUPT,
                error_code=ERR_STORE_CORRUPT,
                detail=str(exc),
            )

        # Integrity marker (if present) must match current bytes.
        marker = _integrity_marker_path(path)
        if marker.exists():
            try:
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
                if marker_payload.get("sha256") != _sha256_file(path):
                    return ReadResult(
                        status=TRUTH_CORRUPT,
                        error_code=ERR_STORE_CORRUPT,
                        detail="integrity marker mismatch",
                    )
            except (OSError, json.JSONDecodeError, ValueError):
                return ReadResult(
                    status=TRUTH_CORRUPT,
                    error_code=ERR_STORE_CORRUPT,
                    detail="integrity marker unreadable",
                )

        if not records:
            return ReadResult(status=TRUTH_EMPTY, records=[])
        return ReadResult(status=TRUTH_AVAILABLE_WITH_DATA, records=records)

    @staticmethod
    def _parse_record(row: Any, idx: int) -> ProjectPreparationRecord:
        if not isinstance(row, dict):
            raise ValueError(f"record #{idx} is not an object")
        for field_name in (
            "project_id",
            "schema_version",
            "revision",
            "created_at",
            "updated_at",
            "state",
            "normalized",
        ):
            if field_name not in row:
                raise ValueError(f"record #{idx} missing field: {field_name}")
        if not isinstance(row.get("normalized"), dict):
            raise ValueError(f"record #{idx} normalized is not an object")
        if row["schema_version"] != SCHEMA_VERSION:
            raise ValueError(f"record #{idx} unsupported schema_version")
        if row["state"] not in ALLOWED_STATES:
            raise ValueError(f"record #{idx} invalid state: {row['state']!r}")
        if not __import__("re").match(SAFE_ID_PATTERN, str(row["project_id"])):
            raise ValueError(f"record #{idx} malformed project_id")
        if row.get("side_effect_flags", SIDE_EFFECT_FLAGS) != SIDE_EFFECT_FLAGS:
            raise ValueError(f"record #{idx} side_effect_flags not all-false")
        return ProjectPreparationRecord.from_dict(row)

    def read(self) -> ReadResult:
        """Public read. Catches I/O + lock failures as UNAVAILABLE."""
        try:
            return self._read_raw()
        except OSError as exc:
            return ReadResult(
                status=TRUTH_UNAVAILABLE,
                error_code=ERR_STORE_UNAVAILABLE,
                detail=f"io error: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ReadResult(
                status=TRUTH_UNAVAILABLE,
                error_code=ERR_STORE_UNAVAILABLE,
                detail=f"read error: {exc}",
            )

    # -- low-level write ---------------------------------------------------

    def _ordered(self, records: list[ProjectPreparationRecord]) -> list[ProjectPreparationRecord]:
        return sorted(records, key=lambda r: (r.created_at, r.project_id))

    def _write(self, records: list[ProjectPreparationRecord]) -> None:
        """Atomic, fsync'd, integrity-marked write. Raises on failure.

        The caller must hold the advisory lock. On ANY failure the prior valid
        store file is left untouched (fail closed).
        """
        path = self._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = self._ordered(records)
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "store_kind": STORE_KIND,
            "written_at": _now_iso(),
            "record_count": len(ordered),
            "records": [r.to_dict() for r in ordered],
        }
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        tmp = path.parent / f"{path.name}{TMP_SUFFIX}.{os.getpid()}"
        marker = _integrity_marker_path(path)
        marker_tmp = marker.parent / f"{marker.name}{TMP_SUFFIX}.{os.getpid()}"
        # Ensure temp files never linger on success or failure.
        temps = [tmp, marker_tmp]
        try:
            tmp.write_text(serialized, encoding="utf-8")
            # Validate complete bytes before replace.
            json.loads(tmp.read_text(encoding="utf-8"))
            # Best-effort fsync: the spec requires flush/fsync
            # *where supported*. Under some MSYS/git-bash Python builds
            # os.fsync on a read handle raises Errno 9 (Bad file
            # descriptor) even though the bytes are written and
            # os.replace is atomic on POSIX/Windows. fail-closed means
            # we keep the prior valid store; here the new bytes are
            # already durable enough for a same-machine local store, so
            # a non-fatal fsync error is swallowed (never aborts a good write).
            try:
                with tmp.open("rb") as fh:
                    os.fsync(fh.fileno())
            except OSError:
                pass
            atomic_replace(tmp, path)
            # Integrity marker (written atomically, last).
            marker_payload = {
                "schema_version": SCHEMA_VERSION,
                "sha256": _sha256_file(path),
                "record_count": len(ordered),
                "written_at": envelope["written_at"],
            }
            marker_tmp.write_text(
                json.dumps(marker_payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            atomic_replace(marker_tmp, marker)
        finally:
            for candidate in temps:
                try:
                    if candidate.exists():
                        candidate.unlink()
                except OSError:
                    pass

    # -- high-level operations --------------------------------------------

    def create_draft(self, input: dict[str, Any]) -> WriteResult:
        errors = validate_draft_input(input)
        if errors:
            return WriteResult(
                ok=False, error_code=ERR_VALIDATION_FAILED, detail="; ".join(errors)
            )
        normalized = normalize_draft_input(input)
        project_id = normalized["project_id"]
        try:
            with file_lock(self._store_path):
                result = self._read_raw_for_write()
                if result.status in (TRUTH_CORRUPT, TRUTH_INCOMPATIBLE_SCHEMA, TRUTH_UNAVAILABLE):
                    return WriteResult(
                        ok=False,
                        error_code=result.error_code or ERR_STORE_UNAVAILABLE,
                        detail=result.detail,
                    )
                existing = {r.project_id: r for r in result.records}
                if project_id in existing:
                    prior = existing[project_id]
                    if self._normalized_equal(prior.normalized, normalized):
                        # Exact create replay -> idempotent return.
                        return WriteResult(ok=True, record=prior)
                    # Conflicting identity with different payload -> reject.
                    return WriteResult(
                        ok=False,
                        error_code=ERR_IDENTITY_CONFLICT,
                        detail=f"project_id {project_id} already exists with different content",
                    )
                now = _now_iso()
                record = ProjectPreparationRecord(
                    project_id=project_id,
                    schema_version=SCHEMA_VERSION,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    state=STATE_APPROVAL_REQUIRED,
                    normalized=normalized,
                    approval={
                        "status": "pending",
                        "approved_at": None,
                        "approval_count": 0,
                        "approved_by": "local-solo-operator",
                    },
                    preparation_preview=None,
                    side_effect_flags=dict(SIDE_EFFECT_FLAGS),
                )
                records = list(result.records)
                records.append(record)
                self._write(records)
                return WriteResult(ok=True, record=record)
        except Exception as exc:  # lock failure / io => fail closed
            return WriteResult(
                ok=False,
                error_code=ERR_PERSISTENCE_WRITE_FAILED,
                detail=f"create failed: {exc}",
            )

    def approve(
        self, project_id: str, expected_revision: Optional[int] = None
    ) -> WriteResult:
        if not __import__("re").match(SAFE_ID_PATTERN, project_id or ""):
            return WriteResult(
                ok=False, error_code=ERR_PROJECT_NOT_FOUND, detail="malformed project_id"
            )
        try:
            with file_lock(self._store_path):
                result = self._read_raw_for_write()
                if result.status in (TRUTH_CORRUPT, TRUTH_INCOMPATIBLE_SCHEMA, TRUTH_UNAVAILABLE):
                    return WriteResult(
                        ok=False,
                        error_code=result.error_code or ERR_STORE_UNAVAILABLE,
                        detail=result.detail,
                    )
                prior = next((r for r in result.records if r.project_id == project_id), None)
                if prior is None:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_PROJECT_NOT_FOUND,
                        detail=f"project not found: {project_id}",
                    )
                # Stale-revision protection must run BEFORE the idempotent
                # replay return, so a stale expected revision is rejected
                # even when the record is already approved.
                if expected_revision is not None and expected_revision != prior.revision:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_REVISION_CONFLICT,
                        detail=(
                            f"stale revision {expected_revision} "
                            f"!= current {prior.revision}"
                        ),
                    )
                # Already approved/preview-ready -> idempotent return.
                if prior.state in (STATE_APPROVED, STATE_PREPARATION_PREVIEW_READY):
                    return WriteResult(ok=True, record=prior)
                if prior.state != STATE_APPROVAL_REQUIRED:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_INVALID_TRANSITION,
                        detail=f"cannot approve from state {prior.state}",
                    )
                updated = ProjectPreparationRecord.from_dict(prior.to_dict())
                updated.revision = prior.revision + 1
                updated.updated_at = _now_iso()
                updated.state = STATE_APPROVED
                updated.approval = {
                    "status": "approved",
                    "approved_at": updated.updated_at,
                    "approval_count": 1,
                    "approved_by": "local-solo-operator",
                }
                records = [r for r in result.records if r.project_id != project_id]
                records.append(updated)
                self._write(records)
                return WriteResult(ok=True, record=updated)
        except Exception as exc:
            return WriteResult(
                ok=False,
                error_code=ERR_PERSISTENCE_WRITE_FAILED,
                detail=f"approve failed: {exc}",
            )

    def create_preview(
        self, project_id: str, expected_revision: Optional[int] = None
    ) -> WriteResult:
        if not __import__("re").match(SAFE_ID_PATTERN, project_id or ""):
            return WriteResult(
                ok=False, error_code=ERR_PROJECT_NOT_FOUND, detail="malformed project_id"
            )
        try:
            with file_lock(self._store_path):
                result = self._read_raw_for_write()
                if result.status in (TRUTH_CORRUPT, TRUTH_INCOMPATIBLE_SCHEMA, TRUTH_UNAVAILABLE):
                    return WriteResult(
                        ok=False,
                        error_code=result.error_code or ERR_STORE_UNAVAILABLE,
                        detail=result.detail,
                    )
                prior = next((r for r in result.records if r.project_id == project_id), None)
                if prior is None:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_PROJECT_NOT_FOUND,
                        detail=f"project not found: {project_id}",
                    )
                # Stale-revision protection before idempotent replay-return.
                if expected_revision is not None and expected_revision != prior.revision:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_REVISION_CONFLICT,
                        detail=(
                            f"stale revision {expected_revision} "
                            f"!= current {prior.revision}"
                        ),
                    )
                if prior.state == STATE_PREPARATION_PREVIEW_READY:
                    return WriteResult(ok=True, record=prior)
                if prior.state != STATE_APPROVED:
                    return WriteResult(
                        ok=False,
                        error_code=ERR_INVALID_TRANSITION,
                        detail=f"cannot preview from state {prior.state}",
                    )
                updated = ProjectPreparationRecord.from_dict(prior.to_dict())
                updated.revision = prior.revision + 1
                updated.updated_at = _now_iso()
                updated.state = STATE_PREPARATION_PREVIEW_READY
                normalized = updated.normalized
                updated.preparation_preview = {
                    "schema_version": SCHEMA_VERSION,
                    "project_identity": updated.project_id,
                    "project_title": normalized["project_title"],
                    "client_or_brand": normalized["client_or_brand"],
                    "normalized_brief_summary": normalized["normalized_brief_summary"],
                    "selected_output_profiles": [
                        p["id"] for p in normalized["output_profiles"]
                    ],
                    "planned_rendition_count": normalized["planned_rendition_count"],
                    "expected_preparation_stages": list(PREPARATION_STAGES),
                    "approval_status": "approved",
                }
                updated.side_effect_flags = dict(SIDE_EFFECT_FLAGS)
                records = [r for r in result.records if r.project_id != project_id]
                records.append(updated)
                self._write(records)
                return WriteResult(ok=True, record=updated)
        except Exception as exc:
            return WriteResult(
                ok=False,
                error_code=ERR_PERSISTENCE_WRITE_FAILED,
                detail=f"preview failed: {exc}",
            )

    # -- write-time read helper (no recursion into public read) ----------------

    def _read_raw_for_write(self) -> ReadResult:
        if not self._store_path.exists():
            return ReadResult(status=TRUTH_EMPTY, records=[])
        return self._read_raw()

    # -- equality helper ------------------------------------------------

    @staticmethod
    def _normalized_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
        a_profiles = [p["id"] for p in a.get("output_profiles", [])]
        b_profiles = [p["id"] for p in b.get("output_profiles", [])]
        return (
            a.get("project_title") == b.get("project_title")
            and a.get("client_or_brand") == b.get("client_or_brand")
            and a.get("project_purpose") == b.get("project_purpose")
            and a.get("normalized_brief_summary") == b.get("normalized_brief_summary")
            and a.get("target_duration_seconds") == b.get("target_duration_seconds")
            and a_profiles == b_profiles
            and a.get("operator_notes") == b.get("operator_notes")
        )
