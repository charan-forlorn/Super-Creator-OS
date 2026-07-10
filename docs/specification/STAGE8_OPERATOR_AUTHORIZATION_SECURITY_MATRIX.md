# Stage 8 Operator Authorization Security Matrix

Stage 8.5 keeps authorization separate from activation.

| Case | Expected decision | Required behavior |
|---|---|---|
| Valid exact human approval | `AUTHORIZED_IN_PRINCIPLE` | Grants future-stage authorization only; all runtime flags remain false |
| Explicit denial | `DENIED` | Preserves reason and grants no authorization |
| Missing operator identity | `BLOCKED` | Requires named operator id, display name, role, and auth evidence ref |
| AI-agent approval attempt | `BLOCKED` | Rejects automated or AI-agent approval identities |
| Blanket approval | `BLOCKED` | Requires per-request approval |
| Wildcard adapter approval | `BLOCKED` | Requires one supported adapter id |
| Adapter mismatch | `BLOCKED` | Requires approval, scope, and preflight adapter to match |
| Runtime mismatch | `BLOCKED` | Requires runtime target binding to the Stage 8.5 authorization flow |
| Request ID mismatch | `BLOCKED` | Requires approval evidence to bind the same request id |
| Timestamp mismatch | `BLOCKED` or `EXPIRED` | Binding mismatch blocks; stale evidence expires |
| Expired authorization | `EXPIRED` | Requires expiry after `checked_at` |
| Stale preflight | `EXPIRED` | Requires current preflight timestamp binding |
| Failed Stage 8.4 preflight | `BLOCKED` | Requires `READY_FOR_OPERATOR_DECISION` and passing required Stage 8.4 checks |
| Secret material present | `BLOCKED` | Rejects secret-like fields and values |
| Unsafe credential reference | `BLOCKED` | Accepts references only, never material |
| Unsupported transport | `BLOCKED` | Requires Stage 8.4 allowed transport mode |
| Missing rollback acknowledgement | `BLOCKED` | Requires explicit rollback acknowledgement |
| Missing fallback acknowledgement | `BLOCKED` | Requires explicit fallback acknowledgement |
| Audit store would write immediately | `BLOCKED` | Audit readiness must not write now |
| Scope exceeds approved operations | `BLOCKED` | Rejects activation, dispatch, credential materialization, and external-call operations |
| Input mutation attempt | Preserved | Models freeze nested input state |
| Invalid report output path | Rejected | URL and path escape output paths are rejected |
| Deterministic repeated evaluation | Preserved | Same input and timestamp produce same result |
| Report redaction verification | Preserved | Report writer validates no secret material before writing |

## Adapter Rows

| Adapter | Identifier | Runtime target | Authorization evidence | Credential material | Activation | Dispatch | Later stage required |
|---|---|---|---|---|---|---|---|
| ChatGPT | `chatgpt` | simulator/manual when bound by evidence | exact human request approval | NO | DISABLED | BLOCKED | YES |
| Claude Code | `claude_code` | simulator/manual when bound by evidence | exact human request approval | NO | DISABLED | BLOCKED | YES |
| Codex | `codex` | simulator/manual when bound by evidence | exact human request approval | NO | DISABLED | BLOCKED | YES |
| Hermes | `hermes` | simulator/manual when bound by evidence | exact human request approval | NO | DISABLED | BLOCKED | YES |
| Unsupported | unknown | none | rejected | NO | DISABLED | BLOCKED | YES |

No row documents real secret formats or credential values.
