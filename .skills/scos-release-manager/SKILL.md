# Skill: scos-release-manager

## Purpose
Assess release readiness and close stages safely: verify evidence, defects, docs, and Git state before any release or stage-closure commit.

## When to Use
- Closing a stage series (e.g., Stage 6 complete) or cutting a release.
- Deciding whether accumulated commits are safe to tag/ship.
- Producing release notes from certified stage history.

## Core Rules
- Release readiness is evidence-based: certification reports, test evidence, and clean Git state are prerequisites, not formalities.
- Known defects must be listed with severity; GO with open critical defects is forbidden.
- Git state verified via scos-git-safety-gate; no release from a dirty or diverged tree.
- No commit, tag, or push without explicit user authorization.
- Release notes describe only what is actually in the included commits.

## Required Output
- Release Target
- Included Commits
- Included Features
- Test Evidence
- Known Defects
- Documentation Status
- Git Status
- Deployment Risk
- GO / NO-GO
- Release Notes

## Prompt Template
```
Act as SCOS Release Manager.
Release target: <version/stage>. Range: <base>..HEAD.
Gather commit list, map to features, collect certification evidence.
Produce the Required Output. GO only if: all included stages certified,
no open critical defects, docs current, Git state clean and synced.
```

## Anti-Scope-Drift Rules
- Assess only the declared range; no last-minute feature or fix additions.
- NO-GO produces a blocker list, not ad-hoc fixes during release assessment.

## Token-Saving Rules
- Included Commits from `git log --oneline <base>..HEAD` verbatim.
- Reference certification reports by path; do not restate their content.
- Release Notes: one line per feature/fix, user-visible wording.
