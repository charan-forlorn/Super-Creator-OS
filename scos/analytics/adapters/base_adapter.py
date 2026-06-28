"""SCOS Stage 3.1 — abstract analytics adapter.

`BaseAnalyticsAdapter` is the platform-independent contract every platform adapter
inherits. It owns the generic CSV loading + structural validation (empty file,
missing required columns, duplicate ids) and enforces the normalize-only-when-valid
rule. Subclasses declare their schema and implement field-level validation +
row→model construction — no core change is ever needed to add a new platform.

Pure stdlib, deterministic, no learning/scoring/persistence.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path

from analytics_models import NormalizedAnalytics


class AnalyticsValidationError(Exception):
    """Raised by normalize() when validate() finds problems. Never auto-fixes."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


class BaseAnalyticsAdapter(ABC):
    """Abstract base for all platform analytics adapters."""

    def __init__(self) -> None:
        self._rows: list[dict] | None = None
        self._fieldnames: list[str] = []
        self._file_path: Path | None = None

    # ------------------------------------------------------------------ #
    # subclass contract
    # ------------------------------------------------------------------ #
    @abstractmethod
    def adapter_name(self) -> str:
        """Stable platform identifier, e.g. 'youtube'."""

    @abstractmethod
    def required_columns(self) -> tuple[str, ...]:
        """CSV columns that MUST be present."""

    @abstractmethod
    def id_column(self) -> str:
        """CSV column holding the unique video id."""

    @abstractmethod
    def _validate_rows(self, rows: list[dict]) -> list[str]:
        """Field-level, per-row validation (numeric/negative/timestamp). Returns
        deterministic error strings in row order."""

    @abstractmethod
    def _build(self, rows: list[dict]) -> list[NormalizedAnalytics]:
        """Construct normalized records from already-validated rows."""

    # ------------------------------------------------------------------ #
    # public API (shared)
    # ------------------------------------------------------------------ #
    def load(self, file_path: str | Path) -> "BaseAnalyticsAdapter":
        """Load a platform CSV deterministically. Returns self for chaining."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"analytics file not found: {p}")
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            self._fieldnames = list(reader.fieldnames or [])
            self._rows = [dict(r) for r in reader]
        self._file_path = p
        return self

    def validate(self) -> list[str]:
        """Return a deterministic list of validation errors ([] = valid)."""
        if self._rows is None:
            return ["adapter not loaded: call load() first"]

        errors: list[str] = []

        # structural: empty CSV
        if not self._rows:
            errors.append("empty CSV: no data rows")
            return errors

        # structural: missing required columns (reported in declared order)
        present = set(self._fieldnames)
        for col in self.required_columns():
            if col not in present:
                errors.append(f"missing required column: {col}")
        if errors:
            return errors  # cannot meaningfully check rows without columns

        # structural: duplicate ids (sorted for determinism)
        idc = self.id_column()
        seen: dict[str, list[int]] = {}
        for i, row in enumerate(self._rows):
            seen.setdefault((row.get(idc) or "").strip(), []).append(i + 1)
        for vid in sorted(k for k, v in seen.items() if len(v) > 1):
            rows = ",".join(str(n) for n in seen[vid])
            errors.append(f"duplicate video id: {vid!r} (rows {rows})")

        # field-level (subclass), appended after structural in row order
        errors.extend(self._validate_rows(self._rows))
        return errors

    def normalize(self) -> list[NormalizedAnalytics]:
        """Return List[NormalizedAnalytics]. Raises AnalyticsValidationError if
        the data is invalid — never auto-fixes, never returns partial output."""
        errors = self.validate()
        if errors:
            raise AnalyticsValidationError(errors)
        return self._build(self._rows or [])

    # ------------------------------------------------------------------ #
    # shared parse helpers (raise ValueError on bad input)
    # ------------------------------------------------------------------ #
    @staticmethod
    def to_int(value: str) -> int:
        v = (value or "").strip().replace(",", "")
        return int(v)

    @staticmethod
    def to_float(value: str) -> float:
        v = (value or "").strip().replace(",", "")
        return float(v)
