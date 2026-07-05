# Shared Reporting Framework — Contract Only (Stage 4.18)

**Status: contract/design document.** Stage 4.18 defines the shared report
vocabulary and rules; it does NOT migrate any Stage 4.1–4.17 report to them.
Existing stage report shapes remain the authoritative contracts for their
stages.

## Purpose

Every Stage 4 feature emits a report/manifest with the same ingredients —
checks, blockers, artifact references, manual next actions, metadata — but
each stage declares its own private dataclasses for them. This contract
names the shared representation so future stages (and eventual migrations)
converge on one vocabulary, backed by `scos.commercial.domain_models`.

## Shared report sections

A conforming report JSON object contains, in this key order:

1. `report_id` — content-derived, deterministic (SHA-256 based, never random).
2. `schema_version` — integer, additive evolution only.
3. `report_type` — stable snake_case stage identifier.
4. `created_at` — caller-supplied ISO-8601 string (never a live clock).
5. `status` — overall verdict (`PASS` / `FAIL` / `BLOCKED`).
6. `checks` — list of shared check objects.
7. `blockers` — list of shared blocker objects.
8. `artifacts` — list of shared evidence references.
9. `manual_actions` — list of shared manual action objects.
10. `metadata` — plain JSON object (FrozenMap-serialized).

## Shared evidence references

`CommercialArtifactReference.to_dict()`:

```json
{
  "artifact_id": "A-001",
  "artifact_type": "manifest",
  "path": "output/.../manifest.json",
  "sha256": "…64 hex chars or null…",
  "required": true,
  "metadata": {}
}
```

Paths are local (URL paths rejected by `validate_no_url_path`); `sha256`
comes from `manifest_tools.sha256_file` when the artifact exists.

## Shared blocker representation

`CommercialBlocker.to_dict()` — keys `blocker_id`, `category`, `severity`
(`warning` | `error` | `critical`), `title`, `detail`,
`recommended_action`, `source`, `metadata`. A report with any
`critical` blocker must carry overall `status: "BLOCKED"`.

## Shared check representation

`CommercialCheck.to_dict()` — keys `check_name`, `status`
(`success` | `failure` | `skipped`), `severity`
(`info` | `warning` | `error` | `critical`), `artifact_path`,
`error_kind`, `error_detail`, `metadata`. `error_kind` values are stable
UPPER_SNAKE identifiers (the existing per-stage vocabulary, e.g.
`INPUT_NOT_FOUND`, `MANUAL_ONLY_VIOLATION`).

## Deterministic JSON rules

- Serialize with `manifest_tools.stable_json_dumps` /
  `write_stable_json`: sorted keys, 2-space indent, trailing newline,
  UTF-8, LF.
- No live clock, no random, no uuid anywhere in a report; timestamps are
  caller-supplied, ids content-derived.
- Tuples serialize as JSON lists; FrozenMap as plain objects.
- Identical inputs must produce byte-identical report files.

## Markdown generation rules

Where a stage renders a human-readable companion (`*.md`) next to a report:

- Generated purely from the report JSON — never from live state.
- Deterministic section order matching the report sections above.
- Tables for checks/blockers/artifacts; one manual action per bullet with
  its priority and `requires_human_review` stated.
- LF line endings, trailing newline, no timestamps beyond the report's own
  `created_at`.

## Compatibility with Stage 4.1–4.17

Existing stage reports already satisfy the deterministic JSON rules (they
share the same `sort_keys=True, indent=2` + trailing newline format and the
no-clock/no-random discipline). Their per-stage dataclasses are structurally
compatible supersets/renames of the shared models (e.g.
`LaunchCertificationCheck` ≈ `CommercialCheck`). Nothing in this contract
changes any serialized output of Stage 4.1–4.17; those schemas remain
frozen under their own `*_SCHEMA_VERSION` constants.

## Future migration approach

Incremental and additive, one stage at a time:

1. New stages (4.19+, Stage 5) adopt the shared models directly.
2. An existing stage migrates only when it needs a schema bump for other
   reasons; the bump maps its private models onto the shared ones and
   increments that stage's `*_SCHEMA_VERSION`.
3. Each migration ships with a regression proof that the stage's previous
   serialized outputs are either byte-identical or explicitly
   version-bumped and documented.
4. Private helper duplicates (`_json_text`, `_sha256_of`, sensitive-key
   scans) are swapped for `validation` / `manifest_tools` calls during the
   same migration, never in a standalone sweep.

## Why Stage 4.18 avoids a big-bang report refactor

Seventeen stage contracts are certified and consumed (tests, UI snapshots,
archived artifacts). Rewriting them at once would risk every one of those
consumers for zero functional gain, invalidate existing certification
evidence, and violate the additive-first rule. The cheap, safe move is what
this stage does: define the shared vocabulary, prove it with its own tests,
and let migrations happen one stage at a time with per-stage proofs.
