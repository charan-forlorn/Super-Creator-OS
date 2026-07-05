# Unified Prompt & Result Packet Contract (Stage 5.4)

## Purpose

Define a single, deterministic envelope format for handing a prompt from
one agent to another (`PromptPacket`), returning a result
(`ResultPacket`), and recording a non-executing recommendation for what
should happen next (`PacketRoutingDecision`). Stage 5.4 answers:

> How does SCOS package a task prompt for one AI, preserve context/evidence,
> receive the result, validate it, and route it to the next AI without
> losing traceability?

Stage 5.4 sits above the Stage 5.2 AI Work Session Manager and the Stage
5.3 AI Agent Adapter Contract Layer. It creates the packet layer only: pure
dataclasses, a builder, and a local JSONL store. It never sends a prompt to
a real AI app, never reads a clipboard, never automates a browser/app/GUI,
and never calls an API or the network.

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, this
module belongs to the **Development Framework Layer**. It must never be
imported by, or embedded into, the Runtime Product Layer, and it changes no
Runtime Product Layer behavior.

## Non-goals

Stage 5.4 is NOT: a ChatGPT/Claude Code/Codex/Hermes integration, an API
client, MCP, a WebSocket server, a database (no SQLite), an HTTP server,
browser automation, GUI automation, AI execution of any kind, clipboard
automation, a background worker or scheduler, git execution (no
commit/push), a SaaS/CRM/payment surface, or a cloud service. It changes no
Runtime Product Layer behavior, mutates no Stage 4/5.1/5.2/5.3 artifact, and
never mutates a Stage 5.1 command queue.

## `FrozenMap`-as-tuple-of-pairs

The task spec's field annotations describe every `metadata` field as a
`FrozenMap`. No `FrozenMap` class exists anywhere in `scos/control_center/`
(one exists in `scos/commercial/report_models.py`, but this package's own
docstrings forbid importing `scos.commercial` in-process). Every sibling
Stage 5.x model already satisfies "immutable map field" via
`tuple[tuple[str, str], ...]` plus a `_string_pairs`/`_pairs_to_lists`
helper pair (see `work_session_models.py`, `agent_adapter_models.py`).
Stage 5.4 follows the same convention for every `metadata` field rather
than inventing a new class — the intent (an immutable, map-shaped field) is
preserved; only the concrete Python type differs from the literal spec
text.

## Schema reference

### `PacketContextReference`

Fields (also the `to_dict()` key order): `ref_id`, `ref_type`, `title`,
`path`, `summary`, `required`, `sha256`, `metadata`.

Allowed `ref_type`: `session`, `stage_plan`, `implementation_report`,
`review_report`, `audit_report`, `file_path`, `git_commit`, `test_result`,
`operator_note`, `specification`, `certification`, `handoff`.

`path` may be `None`; when present it is rejected if it looks like a URL.
`sha256` may be `None` in Stage 5.4 (no content-hash verification is
performed by this stage).

### `PromptPacket`

Fields: `ok`, `schema_version`, `packet_id`, `packet_type`, `session_id`,
`task_id`, `source_agent`, `target_agent`, `target_runtime_id`, `title`,
`objective`, `prompt_body`, `context_refs`, `constraints`,
`expected_result_format`, `expected_artifacts`, `created_at`, `status`,
`metadata`.

Allowed `packet_type`: `planning_prompt`, `implementation_prompt`,
`review_prompt`, `audit_prompt`, `status_update_prompt`,
`result_summary_prompt`, `release_gate_prompt`, `manual_handoff_prompt`.

Allowed agent names (`source_agent`/`target_agent`): `chatgpt`,
`claude_code`, `codex`, `hermes`, `operator`.

Allowed `status`: `drafted`, `ready_for_operator_review`,
`approved_for_handoff`, `sent_to_agent`, `result_expected`, `cancelled`,
`blocked`.

`prompt_body`, `objective`, and `target_agent` must be non-empty.
`created_at` must be caller-supplied (no clock is read). `prompt_body` is
rejected if it contains a `http://`/`https://` URL.

### `ResultArtifactReference`

Fields: `artifact_id`, `artifact_type`, `path`, `summary`, `sha256`,
`required`, `metadata`.

Allowed `artifact_type`: `text_result`, `implementation_report`,
`review_report`, `audit_report`, `test_output`, `changed_files`,
`diff_summary`, `blocker_list`, `decision`, `next_action`,
`certification_report`.

### `ResultPacket`

Fields: `ok`, `schema_version`, `result_packet_id`, `prompt_packet_id`,
`session_id`, `task_id`, `source_agent`, `target_agent`, `result_type`,
`verdict`, `summary`, `artifacts`, `blockers`, `next_action`,
`recommended_next_agent`, `created_at`, `status`, `metadata`.

Allowed `result_type`: `planning_result`, `implementation_result`,
`review_result`, `audit_result`, `status_update_result`, `result_summary`,
`release_gate_result`, `manual_handoff_result`.

Allowed `verdict`: `PASS`, `PASS_WITH_WARNINGS`, `NEEDS_FIX`, `BLOCKED`,
`FAIL`, `INFO`.

Allowed `status`: `received`, `validated`, `review_required`,
`next_prompt_ready`, `archived`, `blocked`.

`summary` must be non-empty. `created_at` must be caller-supplied.
`recommended_next_agent`, when not `None`, must be one of the allowed
agent names.

### `PacketRoutingDecision`

Fields: `decision_id`, `source_result_packet_id`, `next_agent`,
`next_packet_type`, `reason`, `priority`, `requires_operator_approval`,
`metadata`.

Allowed `priority`: `low`, `normal`, `high`, `urgent`.
`requires_operator_approval` defaults to `True` in the builder.
Creating a `PacketRoutingDecision` never sends anything anywhere — see
`AI_PACKET_ROUTING_CONTRACT.md` for the no-auto-dispatch rule.

### `PromptResultPacketError`

Fields: `ok`, `schema_version`, `error_kind`, `error_detail`,
`failed_step`, `metadata`.

Allowed `error_kind` (enum-enforced, mirroring Stage 5.3's
`AgentAdapterError` rather than Stage 5.2's free-form
`AIWorkSessionError.error_kind`, since the builder has many distinct
validation failure modes worth distinguishing): `invalid_agent`,
`invalid_packet_type`, `invalid_result_type`, `invalid_verdict`,
`invalid_ref_type`, `invalid_artifact_type`, `invalid_priority`,
`missing_required_field`, `empty_required_field`, `unsafe_path`,
`unsafe_metadata`, `invalid_collection_type`, `contract_violation`.

## Deterministic ID rules

All ids are content-derived SHA-256 hex digests, truncated to 16 hex
characters, with a short type prefix. IDs are computed by
`prompt_result_packet_builder.py`, never by the models themselves — a
model's `.of()` factory always takes its id as a plain caller-supplied
string.

```
packet_id        = "pp-" + sha256("|".join((session_id, task_id, packet_type,
                                             source_agent, target_agent,
                                             title, created_at)))[:16]

result_packet_id = "rp-" + sha256("|".join((prompt_packet_id, source_agent,
                                             target_agent, result_type,
                                             verdict, created_at)))[:16]

decision_id       = "rd-" + sha256("|".join((source_result_packet_id,
                                              next_agent, next_packet_type,
                                              reason, priority)))[:16]
```

**Never reorder these fields.** The join order is part of the deterministic
contract; reordering it would silently change every historical id. Every
id-derivation field is caller-supplied and stable at construction time — no
clock, no random, no uuid is ever read. `created_at` is deliberately
included in every hash so that re-issuing "the same" packet at a different
time produces a distinct id (e.g. a second implementation attempt after a
fix cycle).

## JSONL storage rules

`scos/control_center/prompt_result_packet_store.py` reuses the existing
`command_queue._append_jsonl_line` / `_read_jsonl_objects` primitives:
UTF-8, LF, one compact JSON object per line, local paths only
(`http://`/`https://`/any `scheme://` path is rejected), parent directories
created automatically, strictly append-only (no line is ever deleted,
truncated, or rewritten).

Unlike `work_session_store.py` (which replays "latest snapshot wins" per
`session_id`, because an `AIWorkSession` mutates over its lifecycle),
packets and routing decisions are immutable, single-write records — a
follow-up prompt always gets its own distinct `packet_id`. So every loader
in this store is a simple "one line -> one dataclass, in append order"
replay with no de-duplication pass.

Deterministic output is achieved via each model's explicit `to_dict()` key
order, not via `json.dumps(sort_keys=True)` — the shared
`_append_jsonl_line` primitive (reused as-is from `command_queue.py`, not
modified for Stage 5.4) does not pass `sort_keys=True`. This is
functionally equivalent determinism through a different mechanism than a
literal reading of "sort_keys" might suggest.

Document-only default paths (no function reads or writes to these
automatically — every function takes an explicit `path`):

- `scos/work/control_center/prompt_packets.jsonl`
- `scos/work/control_center/result_packets.jsonl`
- `scos/work/control_center/packet_routing_decisions.jsonl`

## Packet lifecycle

`PromptPacket.status` progression (in prose; no state-machine enforcement
is implemented in Stage 5.4 — see "Recommended next stage" in
`docs/certification/Stage-5.4-plan.md`):

```
drafted -> ready_for_operator_review -> approved_for_handoff
        -> sent_to_agent -> result_expected
```

(`cancelled` and `blocked` are terminal off-ramps from any non-terminal
status.)

`ResultPacket.status` progression:

```
received -> validated -> (review_required | next_prompt_ready)
                       -> (archived | blocked)
```

## Relation to `AIWorkSession` and `AgentAdapter` contracts

Packets reference Stage 5.2 `session_id`/`task_id` and Stage 5.3
agent/runtime names purely as opaque strings — this module never imports
`work_session_models.py`, `agent_adapter_models.py`, or any other sibling
Stage 5.x module. The coupling is loose and one-directional: a `PromptPacket`
can be thought of as "the next envelope layer" above a Stage 5.3
`AgentAdapterRequest`/`AgentAdapterResult` pair, and its `session_id`/
`task_id` are expected to match an `AIWorkSession`'s own identifiers, but
Stage 5.4 never reads or writes a Stage 5.2 or 5.3 file.

## `manual_clipboard` / operator-approval boundary

Stage 5.4 never touches a clipboard and never sends a packet anywhere.
`"operator"` is a first-class agent name in `ALLOWED_PACKET_AGENT_NAMES`
precisely so that manual handoff can be a first-class terminal target
(`manual_handoff_prompt`) rather than a special case. Every
`PacketRoutingDecision` defaults `requires_operator_approval=True` in the
builder — routing recommendations are advisory only until a human (or a
later stage) acts on them.

## Safety constraints recap

- Every `path` field (on `PacketContextReference` and
  `ResultArtifactReference`) and every value inside every `metadata` pair
  is rejected if it contains `http://` or `https://` (case-insensitive).
- Every `metadata` field is rejected if any key contains `api_key`,
  `token`, `secret`, `password`, or `private_key` (case-insensitive
  substring match).
- `prompt_body`, `objective`, `target_agent` (on `PromptPacket`), `summary`
  (on `ResultPacket`), and `reason` (on `PacketRoutingDecision`) must be
  non-empty.
- No clock, no random, no uuid anywhere in
  `scos/control_center/prompt_result_packet_*.py`.
