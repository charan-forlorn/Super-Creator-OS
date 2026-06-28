# Versioning

> Status: Approved (see [DOCUMENT_LIFECYCLE.md](DOCUMENT_LIFECYCLE.md))

Versioning scheme for the Development AI Layer itself, plus a compatibility statement against SCOS/Knowledge Layer versions.

## Version history

| Version | Contents | Status |
|---|---|---|
| v1.0 | `development/ai/` policy docs, `development/benchmarks/`, `development/evaluation/` | Approved |
| v1.1 | `development/templates/`, `development/playbooks/`, `development/checklists/`, `development/examples/` | Approved |
| v1.1.1 | `development/governance/`, `development/anti-patterns/`, reshaped `checklists/MODEL_SELECTION.md` | Approved |

## Versioning scheme

`MAJOR.MINOR.PATCH` for this layer:

- **MAJOR** — a change that breaks an existing workflow/playbook reference (e.g. removing or renaming a governing document).
- **MINOR** — a new directory or capability added without breaking existing references (e.g. v1.0 → v1.1, v1.1 → v1.1.1 as used above — note "v1.1.1" here is used as the user's chosen label for this addition, not a strict patch-level bugfix; future minor additions should increment the middle number, e.g. v1.2).
- **PATCH** — a correction within an existing document that doesn't add new structure (e.g. fixing a broken cross-reference).

## Compatibility statement

| Development AI Layer version | Compatible with SCOS stage | Minimum Knowledge Layer |
|---|---|---|
| v1.0 | SCOS Stage 3 | Knowledge Layer ≥ 2.9 *(illustrative — confirm against the actual Knowledge Layer version in use before relying on this)* |
| v1.1 | SCOS Stage 3 | Knowledge Layer ≥ 2.9 *(illustrative)* |
| v1.1.1 | SCOS Stage 3 | Knowledge Layer ≥ 2.9 *(illustrative)* |

This layer has no runtime dependency on SCOS or the Knowledge Layer — compatibility here means *documentation relevance* (e.g. references to certified modules assume a given SCOS stage's module set exists), not a technical/API dependency. When SCOS advances to a new stage, or the Knowledge Layer version changes, update this table to state the new minimum and note what (if anything) in `development/ai/` needs re-checking as a result — e.g. new certified modules may warrant new rows in [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md)'s production-directory list.
