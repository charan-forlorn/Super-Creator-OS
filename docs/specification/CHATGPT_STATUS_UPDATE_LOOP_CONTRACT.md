# ChatGPT Status Update Loop Contract (Stage 5.7)

## How Intake Becomes a ChatGPT Status Update

`result_intake_builder.build_chatgpt_status_update_packet(...)` (wrapped by
`chatgpt_status_update.prepare_chatgpt_status_update(...)`) takes an
`AIResultIntakeRecord` and produces a `ChatGPTStatusUpdatePacket`:

- `target_agent` is always `"chatgpt"` (enforced by
  `ALLOWED_CHATGPT_TARGET_AGENTS = ("chatgpt",)`).
- `status_update_body` is composed deterministically from the intake's
  session/task ids, source agent, verdict, normalized summary, blockers,
  warnings, tests summary, changed files summary, evidence references, and
  the requested ChatGPT action — see `_compose_status_update_body(...)` in
  `result_intake_builder.py`.
- `evidence_refs` is derived from the intake's artifacts (`path` if present,
  else `artifact_id`).
- `source_agent` is recorded as a `metadata` entry on the packet (the packet
  model itself has no dedicated `source_agent` field) so the Markdown
  renderer can surface it without re-deriving it from the intake.
- `update_packet_id` is a deterministic `sha256` derivation (see
  `AI_RESULT_INTAKE_CONTRACT.md`).

## Requested ChatGPT Actions

`requested_chatgpt_action` must be one of:

- `summarize_status`
- `decide_next_action`
- `update_stage_plan`
- `prepare_review_prompt`
- `prepare_fix_prompt`
- `prepare_commit_recommendation`
- `mark_blocked`
- `request_operator_decision`

These are labels only — none of them triggers any actual ChatGPT call. They
tell the operator what they should ask ChatGPT to do once they paste the
status update body in manually.

## Markdown Rendering

`chatgpt_status_update.render_chatgpt_status_update_markdown(packet)` renders
a `ChatGPTStatusUpdatePacket` as deterministic Markdown, always including:

- Session id, task id, source agent (read from `packet.metadata`), and
  verdict.
- The full `status_update_body`.
- An `## Evidence` section listing every `evidence_ref` (or `- None`).
- The `requested_chatgpt_action`.
- A fixed `## Constraints` section (see below).
- A closing note that this is a manual handoff artifact and nothing is sent
  automatically.

Rendering the same packet twice always produces byte-identical Markdown.

## Manual Handoff Only

This entire loop is manual-handoff only:

- No function in `chatgpt_status_update.py` opens a network connection,
  calls the ChatGPT API, automates a browser, or touches
  `navigator.clipboard`.
- The Control Center UI (`ChatGPTStatusUpdatePanel`) renders the status
  update body in a read-only `<pre>` block and shows a disabled "Copy
  (disabled)" control — the operator must copy the text themselves.

## Constraints

Every rendered status update carries these fixed constraints, so a human (or
ChatGPT, once pasted) does not over-claim what happened:

- Do not assume hidden files.
- Do not claim work committed/pushed unless evidence says so.
- Produce next action only from provided evidence.

## Future Integration Notes

If a later stage introduces a real ChatGPT API integration, it must:

- Keep `build_chatgpt_status_update_packet` / `prepare_chatgpt_status_update`
  as the single source of packet content — a future dispatch layer should
  consume the packet, not reimplement its composition.
- Introduce dispatch as an explicitly separate, opt-in module so this
  contract's "manual handoff only" guarantee remains true for anyone who
  has not adopted the new integration.
- Continue to require `operator_review_required` / operator approval before
  any automatic send, consistent with `PROJECT_STATE_UPDATE_CONTRACT.md`'s
  approval rule.
