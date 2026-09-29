"""Deterministic quality analysis for repository-local Agent Skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillQuality:
    state: str
    routing: str
    description: str
    issues: tuple[str, ...]
    warnings: tuple[str, ...]
    signals: tuple[tuple[str, bool], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "routing": self.routing,
            "description": self.description,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "signals": [[name, value] for name, value in self.signals],
        }


def _has_section(lines: list[str], *names: str) -> bool:
    wanted = {name.strip().casefold() for name in names}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().casefold()
            if heading in wanted:
                return True
    return False


def _has_routing_signal(lines: list[str], description: str) -> bool:
    lowered_description = description.casefold()
    routing_markers = (
        "use when",
        "use this skill when",
        "trigger when",
        "trigger only when",
        "use after",
        "especially when",
    )
    if any(marker in lowered_description for marker in routing_markers):
        return True
    return _has_section(
        lines,
        "When to Use",
        "When To Use",
        "Use When",
        "Triggers",
        "Routing",
        "Trigger Conditions",
    )


def _has_core_rules_signal(lines: list[str]) -> bool:
    if _has_section(
        lines,
        "Core Rules",
        "Rules",
        "Operating Rules",
        "Core Boundary",
        "Workflow",
    ):
        return True
    return any(
        line.strip().casefold().startswith(("**core principle:**", "**core boundary:**"))
        for line in lines
    )


def _description(lines: list[str]) -> str:
    for line in lines[:40]:
        stripped = line.strip()
        if stripped.casefold().startswith("description:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    for i, line in enumerate(lines[:60]):
        if line.strip().casefold() in {"## purpose", "### purpose"}:
            for candidate in lines[i + 1 : i + 8]:
                value = candidate.strip()
                if value and not value.startswith("#"):
                    return value
    for line in lines[:40]:
        value = line.strip()
        if value and not value.startswith("#") and not value.startswith("---"):
            return value[:280]
    return ""


def analyze_skill(skill_path: str | Path) -> SkillQuality:
    path = Path(skill_path)
    issues: list[str] = []
    warnings: list[str] = []

    if path.name != "SKILL.md":
        issues.append("skill_path must point to SKILL.md")
    if not path.is_file():
        issues.append("SKILL.md is missing")
        return SkillQuality(
            state="DEFECT",
            routing="MISSING",
            description="",
            issues=tuple(issues),
            warnings=(),
            signals=(),
        )

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        issues.append(f"SKILL.md could not be read: {type(exc).__name__}")
        return SkillQuality(
            state="DEFECT",
            routing="UNREADABLE",
            description="",
            issues=tuple(issues),
            warnings=(),
            signals=(),
        )

    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        issues.append("SKILL.md is empty")

    description = _description(lines)
    if not description:
        issues.append("description or purpose is missing")

    when_to_use = _has_routing_signal(lines, description)
    core_rules = _has_core_rules_signal(lines)
    required_output = _has_section(
        lines,
        "Required Output",
        "Output Contract",
        "Expected Output",
        "Required Output for New Surfaces",
    )
    safety = _has_section(lines, "Safety", "Safety Rules", "Constraints", "Boundaries", "Core Boundary")
    references = (path.parent / "references").is_dir()
    scripts = (path.parent / "scripts").is_dir()

    if not when_to_use:
        warnings.append("routing metadata is missing")
    if not core_rules:
        warnings.append("core rules section is missing")
    if not required_output:
        warnings.append("required output contract is missing")
    if len(lines) > 500:
        warnings.append("SKILL.md is long; consider progressive disclosure into references/scripts")
    duplicate_headings = len(
        [line.strip().casefold() for line in lines if line.lstrip().startswith("#")]
    ) - len(
        {
            line.strip().casefold()
            for line in lines
            if line.lstrip().startswith("#")
        }
    )
    if duplicate_headings:
        warnings.append("duplicate headings detected")

    routing = "READY" if when_to_use else "WEAK"
    signals = (
        ("description", bool(description)),
        ("when_to_use", when_to_use),
        ("core_rules", core_rules),
        ("required_output", required_output),
        ("safety", safety),
        ("scripts", scripts),
        ("references", references),
    )

    if issues:
        state = "DEFECT"
    elif warnings:
        state = "WARN"
    else:
        state = "READY"

    return SkillQuality(
        state=state,
        routing=routing,
        description=description[:280],
        issues=tuple(dict.fromkeys(issues)),
        warnings=tuple(dict.fromkeys(warnings)),
        signals=signals,
    )


__all__ = ["SkillQuality", "analyze_skill"]
