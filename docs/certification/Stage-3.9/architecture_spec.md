# SCOS Stage 3.9 Architecture Specification

Status: HISTORICAL ARCHITECTURE SPEC - CERTIFIED BY Stage-3.9.json

Stage: 3.9 - Knowledge Access Layer

## Purpose

Stage 3.9 adds the consumer-facing access boundary over the certified Knowledge
Layer. It lets future consumers such as Stage 4 decision logic, CLI views, and
dashboards depend on one stable read interface instead of binding directly to
Stage 3.5-3.8 internals.

## Layer Position

```text
KnowledgeIndex -> Query -> Explain -> ExplainFacade -> Insight -> KnowledgeService
```

The Stage 3.9 layer is read-only. It composes and projects facts already returned
by the certified Stage 3.6 Query and Stage 3.8 Insight layers. It does not create
knowledge, infer missing facts, rank, score, recommend, persist, or mutate state.

## Scope

In scope:

- `scos/knowledge/knowledge_service.py`
- `scos/knowledge/knowledge_view_models.py`
- `scos/knowledge/tests/test_knowledge_service.py`
- Stage 3.9 draft certification artifacts under `docs/certification/Stage-3.9*`
- Repository entry-point documentation for the Knowledge Access task route

Out of scope:

- Any change to certified Stage 3.5-3.8 implementation files
- Any certification, commit, tag, or release action
- Root duplicate cleanup
- Full system-wide enumeration beyond explicit caller-provided scopes

## Public API

`KnowledgeService` exposes exactly four public methods:

- `knowledge_view(style_id)`
- `run_view(run_id)`
- `portfolio_view(scope)`
- `overview(scope)`

All methods return either an access-layer view model or an access-layer error
model. Errors are returned, never raised for expected not-found, unavailable, or
invalid-scope cases.

## Contracts

- The service may import `KnowledgeInsightEngine`, `KnowledgeQueryEngine`,
  `insight_models`, `query_models`, and `knowledge_view_models`.
- Lower-layer model imports are allowed only for `isinstance` dispatch.
- View models must not import lower-layer modules.
- Returned objects must be access-owned immutable dataclasses.
- Lower-layer payload dictionaries must be copied into access-owned immutable
  projections before being exposed.
- `to_dict()` may emit JSON-friendly dictionaries and lists for consumers.
- The service must not use filesystem helpers, path mutation, persistence,
  network, random, wall-clock, `IndexStore`, or `open()`.
- Explicit portfolio/system scope is required; no global enumeration is added.
- Scope input must be deterministic:
  - `None` and empty scopes return `EmptyScope`.
  - unsupported scope objects and malformed scopes return `ViewUnavailable`.
  - strings and scalar values are not treated as iterables of style IDs.
- Portfolio `view_id` must be deterministic and unique for the explicit style-ID
  set, not only for resolved style count.

## Acceptance Criteria

- Stage 3.9 focused suite passes.
- Stage 3.5-3.8 knowledge suites still pass.
- Static checks confirm no service import-path mutation and no forbidden boundary
  dependencies.
- Public API count test confirms exactly four public methods.
- Error `to_dict()` contract tests cover every access-layer error model.
- Stage 3.9 certification status is recorded by `../Stage-3.9.json`.
