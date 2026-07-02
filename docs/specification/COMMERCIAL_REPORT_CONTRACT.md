# Commercial Report Contract

Status: Stage 4.1 implemented contract
Schema version: 1

## Purpose

The Commercial Report Contract defines the local, immutable report object used
by Stage 4.1. It is a commercial-owned projection over the Stage 3.9
KnowledgeService public boundary. It does not create knowledge, infer missing
facts, call an LLM, upload data, perform network requests, or package delivery.

## Public Model

`CommercialReport` is a frozen dataclass with these required fields:

- `report_id`
- `schema_version`
- `report_type`
- `created_at`
- `source_run_id`
- `style_id`
- `qa_status`
- `summary`
- `evidence`
- `recommendations`
- `risks`
- `metadata`

The schema version is stamped from `COMMERCIAL_REPORT_SCHEMA_VERSION = 1`.
`to_dict()` returns a deterministic, JSON-safe dictionary with stable key order.

## Builder Contract

`build_commercial_report(knowledge_service, run_id, *, now_fn, report_type,
qa_status, risks)` builds one report for a run.

Rules:

- The only Stage 3.9 service call is `KnowledgeService.run_view(run_id)`.
- `created_at` comes from injected `now_fn`.
- Missing or invalid `run_id` returns `CommercialReportError`.
- Expected unavailable/not-found states return `CommercialReportError`.
- Raw exceptions are caught at the boundary and converted to deterministic error
  objects without traceback leakage.
- Recommendations remain an empty tuple unless explicit evidence-backed support
  is added in a later stage.
- Risks are evidence-only: explicit report inputs or public access-layer missing
  evidence/unavailable states.

## Boundary Rules

Commercial code must not import or consume:

- `KnowledgeIndex`
- `KnowledgeQueryEngine`
- `KnowledgeExplainEngine`
- `KnowledgeInsightEngine`
- `query_engine`
- `explain_engine`
- `insight_engine`
- lower-layer query/explain/insight model modules

Commercial code may consume only `KnowledgeService` and commercial-owned models.

## Immutability And Serialization

Nested mappings and sequences are copied into tuple-backed immutable structures
at model construction. `to_dict()` emits plain dictionaries and lists for JSON
serialization, but the report object itself does not expose mutable dict/list
state.

## Non-Goals

Stage 4.1 does not implement delivery packaging, CLI delivery flow, web
dashboard, auth, payment, cloud upload, SaaS behavior, network behavior, or
LLM-generated reports.
