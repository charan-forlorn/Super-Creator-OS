# Stage 8 Adapter Activation Security Matrix

Stage 8.4 keeps every adapter disabled and every dispatch path blocked.

| Adapter | Identifier | Expected mode | Future credential category | Credential material in Stage 8.4 | Allowed transport evidence | Forbidden transport | Operator approval | Audit | Rollback | Simulator fallback | Manual fallback | Activation | Dispatch | Stage 8.4 meaning | Later stage required |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ChatGPT | `chatgpt` | simulator or manual | API key or token category only | NO | manual file snapshot or no transport | WebSocket, SSE, polling, local HTTP, timers, watchers, workers | explicit adapter-specific presentation approval | append-only readiness only | restore disabled state | required | required | DISABLED | BLOCKED | ready for later operator decision only | YES |
| Claude Code | `claude_code` | simulator or manual | API key or token category only | NO | manual file snapshot or no transport | WebSocket, SSE, polling, local HTTP, timers, watchers, workers | explicit adapter-specific presentation approval | append-only readiness only | restore disabled state | required | required | DISABLED | BLOCKED | ready for later operator decision only | YES |
| Codex | `codex` | simulator or manual | API key or token category only | NO | manual file snapshot or no transport | WebSocket, SSE, polling, local HTTP, timers, watchers, workers | explicit adapter-specific presentation approval | append-only readiness only | restore disabled state | required | required | DISABLED | BLOCKED | ready for later operator decision only | YES |
| Hermes | `hermes` | simulator or manual | API key or token category only | NO | manual file snapshot or no transport | WebSocket, SSE, polling, local HTTP, timers, watchers, workers | explicit adapter-specific presentation approval | append-only readiness only | restore disabled state | required | required | DISABLED | BLOCKED | ready for later operator decision only | YES |
| Unsupported | unknown | none | unknown | NO | none | all runtime transport | rejected | rejected | required before support | unavailable | manual only | DISABLED | BLOCKED | blocked unsupported adapter | YES |

No row documents real secret formats or credential examples.
