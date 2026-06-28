# Workflow — Claude → Ollama Fallback Handoff

The specific handoff steps when a task already in progress on Claude needs to continue on a local model because Claude becomes unavailable mid-session. For the full decision flow and recovery procedure, see [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md) — this file covers the *handoff mechanics* only.

## Handoff steps

1. Capture state: what has been done so far, what remains, and any constraints discovered mid-task that weren't in the original prompt.
2. Re-express the remaining work as a fresh prompt using the matching template in [prompts/](../prompts/) — do not assume the local model has any memory of the Claude session.
3. Confirm the remaining work doesn't trip an escalation trigger from [ROUTING_RULES.md](../ROUTING_RULES.md) (production-directory touch, architecture-level reasoning). If it does, the remaining work queues for Claude instead of continuing on the local model — see step 6 of [ollama.md](ollama.md).
4. Proceed via the standard [ollama.md](ollama.md) loop from there, tagging the eventual commit `[fallback:<model>]`.

## Handoff is not silent

A handoff mid-task is recorded the same way a fresh fallback task would be — there is no partial-credit distinction between "started on Claude, finished on Ollama" and "entirely on Ollama" for review purposes. Both get the recovery-pass review in [FALLBACK_WORKFLOW.md](../FALLBACK_WORKFLOW.md) once Claude returns.
