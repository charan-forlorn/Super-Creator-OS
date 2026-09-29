"""Focused tests for deterministic Skill quality analysis."""

from pathlib import Path

from scos.control_center.skill_quality import SkillQuality, analyze_skill


def _write_skill(root: Path, body: str) -> Path:
    skill = root / ".skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(body, encoding="utf-8")
    return skill


def test_ready_skill_has_routing_and_contract_signals(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        """# Demo
Description: A deterministic demo skill.

## When to Use
Use this for bounded examples.

## Core Rules
- Read first.
- Fail closed.

## Required Output
Return a verified result.

## Safety
Never mutate production.
""",
    )

    result = analyze_skill(skill)

    assert isinstance(result, SkillQuality)
    assert result.state == "READY"
    assert result.routing == "READY"
    assert result.issues == ()
    assert dict(result.signals)["when_to_use"] is True


def test_missing_routing_is_warning_not_false_defect(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "# Demo\n\nDescription: no routing yet.\n")

    result = analyze_skill(skill)

    assert result.state == "WARN"
    assert result.routing == "WEAK"
    assert "routing metadata is missing" in result.warnings


def test_missing_skill_file_is_defect(tmp_path: Path) -> None:
    result = analyze_skill(tmp_path / ".skills" / "missing" / "SKILL.md")

    assert result.state == "DEFECT"
    assert result.issues == ("SKILL.md is missing",)


def test_long_skill_is_progressive_disclosure_warning(tmp_path: Path) -> None:
    body = "# Demo\n\nDescription: long skill.\n\n" + ("detail\n" * 501)
    skill = _write_skill(tmp_path, body)

    result = analyze_skill(skill)

    assert result.state == "WARN"
    assert any("progressive disclosure" in warning for warning in result.warnings)


def test_frontmatter_routing_and_core_principle_are_recognized(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        """---
name: frontmatter-demo
description: Use when a bounded example needs deterministic verification.
---

# Demo

**Core principle:** Evidence before assertions.
""",
    )

    result = analyze_skill(skill)

    assert result.routing == "READY"
    assert dict(result.signals)["core_rules"] is True
    assert "routing metadata is missing" not in result.warnings
    assert "core rules section is missing" not in result.warnings