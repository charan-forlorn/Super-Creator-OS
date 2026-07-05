# AI Packet Routing Contract (Stage 5.4)

## Purpose

Define the deterministic routing *recommendations* that connect one
`ResultPacket` to the next `PromptPacket` in the ChatGPT -> Claude Code ->
Codex -> Hermes -> ChatGPT flow. Stage 5.4 only ever recommends — it never
executes a routing decision automatically.

## Supported routing cases

Recommendation table, keyed by `(result_type, verdict)`, implemented as
`prompt_result_packet_builder._ROUTING_RECOMMENDATIONS` and exposed via
`recommend_routing(*, result_type, verdict, alternate=False)`:

| `result_type`             | `verdict`  | Recommendation                              |
| -------------------------- | ---------- | -------------------------------------------- |
| `planning_result`           | `PASS`     | `claude_code` / `implementation_prompt`       |
| `implementation_result`     | `PASS`     | `codex` / `review_prompt`                     |
| `implementation_result`     | `NEEDS_FIX`| `claude_code` / `implementation_prompt`       |
| `review_result`             | `PASS`     | `hermes` / `audit_prompt` (primary)           |
| `review_result`             | `PASS`     | `chatgpt` / `status_update_prompt` (alternate, via `alternate=True`) |
| `review_result`             | `NEEDS_FIX`| `claude_code` / `implementation_prompt`       |
| `audit_result`              | `PASS`     | `chatgpt` / `status_update_prompt`            |
| `audit_result`              | `BLOCKED`  | `operator` / `manual_handoff_prompt`          |
| *any* `result_type`         | `FAIL`     | `operator` / `manual_handoff_prompt` (universal escalation) |
| *any* `result_type`         | `BLOCKED`  | `operator` / `manual_handoff_prompt` (universal escalation) |

The universal `FAIL`/`BLOCKED` escalation takes precedence over any
`result_type`-specific entry — it is checked first inside
`recommend_routing`, so a `FAIL` or `BLOCKED` verdict always routes to
`operator`/`manual_handoff_prompt` regardless of which stage produced it.

Any `(result_type, verdict)` combination not listed above (e.g.
`status_update_result` + `INFO`) has no recommendation — `recommend_routing`
returns `None`.

## Worked 5-stage example

```
ChatGPT   planning_prompt  -> planning_result       PASS
                                  |
                                  v  recommend_routing -> (claude_code, implementation_prompt)
Claude Code  implementation_prompt -> implementation_result  NEEDS_FIX
                                  |
                                  v  recommend_routing -> (claude_code, implementation_prompt)  [loops back]
Claude Code  implementation_prompt -> implementation_result  PASS
                                  |
                                  v  recommend_routing -> (codex, review_prompt)
Codex     review_prompt        -> review_result           PASS
                                  |
                                  v  recommend_routing -> (hermes, audit_prompt)
Hermes    audit_prompt         -> audit_result             PASS
                                  |
                                  v  recommend_routing -> (chatgpt, status_update_prompt)
ChatGPT   status_update_prompt -> status_update_result
```

FAIL/BLOCKED-anywhere example: if the Hermes audit instead returns
`audit_result` / `BLOCKED`, `recommend_routing` returns
`(operator, manual_handoff_prompt)` instead of continuing to ChatGPT — the
operator receives a manual handoff packet rather than the automated chain
continuing.

## No-auto-dispatch rule

`recommend_routing()` is a pure lookup function: it returns a
`(next_agent, next_packet_type)` tuple or `None`, and does nothing else.
`create_routing_decision()` builds an immutable `PacketRoutingDecision`
record from that recommendation, and does nothing else. Nothing in
`scos/control_center` reads a `PacketRoutingDecision` and automatically
builds/sends the next `PromptPacket` — the caller must explicitly call
`create_followup_prompt_from_result(...)` as a separate, deliberate step
(today: a human; potentially a future Stage 5.5+ orchestrator, still gated
by operator approval).

## Operator approval requirement

`PacketRoutingDecision.requires_operator_approval` defaults to `True` in
`create_routing_decision(...)`. In current Stage 5.4 usage every routing
decision is created with this flag `True` — there is no code path that sets
it `False`. The flag exists for forward-compatibility (a future stage may
introduce a narrow, explicitly-approved auto-routing case), but Stage 5.4
itself never produces an unapproved routing decision.
