# Operator Packet Review Contract (Stage 5.5)

## Purpose

Define the local-only operator review layer above Stage 5.4 prompt/result
packets. Stage 5.5 answers:

> How does the operator safely review a packet, approve or reject the routing
> decision, prepare a manual handoff package, and record the decision without
> dispatching to real AI apps?

The review layer consumes Stage 5.4 `PromptPacket`, `ResultPacket`, and
`PacketRoutingDecision` objects as data. It produces deterministic
`OperatorPacketDecision` and `OperatorPacketReviewResult` records, plus an
optional `ManualHandoffPackage`.

## Non-goals

Stage 5.5 does not send prompts to ChatGPT, Claude Code, Codex, or Hermes. It
does not read or write the clipboard, automate browsers/apps/GUI, call a
network/API/cloud service, create a server, use WebSockets, poll, run
background workers, use a database, mutate the Stage 5.1 command queue, or
alter Stage 4 or Runtime Product Layer behavior.

## Relation to Stage 5.4 Packets

Stage 5.4 creates packet envelopes and non-executing routing recommendations.
Stage 5.5 reviews those packets before any future dispatch integration exists.
Routing remains advisory until the operator records a decision. A review may
reference:

- `PromptPacket.packet_id`
- `ResultPacket.result_packet_id`
- `PacketRoutingDecision.decision_id`
- target agent/runtime metadata from the packet or routing decision

## Relation to Approval-first Command Bridge

Stage 5.1 established the approval-first principle for local commands. Stage
5.5 applies the same principle to packet routing: no packet is dispatched by
the review layer, and no command queue is mutated. The output is only local
data for the operator to inspect or use manually.

## Data Models

All models are immutable dataclasses in
`scos/control_center/operator_packet_review_models.py`, with
`OPERATOR_PACKET_REVIEW_SCHEMA_VERSION = 1`.

- `PacketReviewCheck`: one validation or safety check.
- `OperatorPacketDecision`: approve/reject/request-changes/manual-handoff/
  blocked decision.
- `ManualHandoffInstruction`: one deterministic operator step.
- `ManualHandoffPackage`: local file package metadata.
- `OperatorPacketReviewResult`: successful review result.
- `OperatorPacketReviewError`: deterministic structured failure.

Every model exposes `to_dict()` with explicit key order. Tuple fields serialize
as lists. Metadata uses a local immutable `FrozenMap` and serializes as a plain
dict. No model exposes mutable list/dict fields.

## Decision Lifecycle

```
PromptPacket / ResultPacket / PacketRoutingDecision
  -> validate_packet_for_operator_review
  -> OperatorPacketDecision
  -> optional ManualHandoffPackage
  -> OperatorPacketReviewResult or OperatorPacketReviewError
  -> optional JSONL append by caller
```

Supported decisions:

- `approve`: valid only when packet checks pass. It creates no handoff package
  unless `create_handoff=True`.
- `reject`: records a rejection reason and never creates a handoff package.
- `request_changes`: preserves the packet reference and never creates a
  handoff package.
- `manual_handoff`: requires target agent/runtime and `create_handoff=True`.
- `blocked`: records a blocker reason and never dispatches.

## Validation Rules

The review logic rejects:

- empty or unsupported decisions
- unsupported `decided_by`
- empty reason
- missing caller-supplied `decided_at`
- unsupported target agents
- URL-like paths in context references or artifact references
- metadata keys containing `api_key`, `token`, `secret`, `password`, or
  `private_key`
- `manual_handoff` without target agent/runtime
- `manual_handoff` without `create_handoff=True`
- `create_handoff=True` without `handoff_output_dir`

Unsupported target runtime ids are rejected only when local runtime validation
can prove they are invalid. If local validation data is insufficient, the review
records a warning check rather than failing.

## Deterministic ID Rules

Decision, handoff, review, and instruction ids are SHA-256 derived from stable
caller-supplied fields and truncated to 16 hex characters with type prefixes.
The code never uses a real clock, random number generator, or uuid. Timestamps
such as `decided_at`, `created_at`, and `reviewed_at` are caller-supplied only.

## JSONL Storage Rules

`scos/control_center/operator_packet_review_store.py` provides:

- `append_operator_packet_decision(path, decision)`
- `append_operator_packet_review_result(path, result)`
- `load_operator_packet_decisions(path)`
- `load_operator_packet_review_results(path)`

Rules:

- path must be local (`http://`, `https://`, and `scheme://` are rejected)
- parent directories are created as needed
- UTF-8, LF, one JSON object per line
- deterministic `json.dumps(sort_keys=True, separators=(",", ":"))`
- append order is preserved
- malformed JSONL fails fast with stable errors
- no SQLite, file locks, background workers, or hidden default writes

Document-only default paths:

- `scos/work/control_center/operator_packet_decisions.jsonl`
- `scos/work/control_center/operator_packet_review_results.jsonl`
- `scos/work/control_center/manual_handoffs/`

## Safety Constraints

Stage 5.5 is local-first and approval-first. It has no automatic dispatch rule:
creating or approving a review result never sends data to an AI app. It has no
clipboard/app/browser automation rule: manual handoff packages are files for a
human to use manually outside SCOS.
