# Fallback Workflow

What happens when Claude Code is unavailable mid-development, and how work done during fallback gets reconciled once Claude returns.

## Decision flow

```text
            Task arrives
                 |
                 v
       Is Claude available?
                 |
        +--------+--------+
        |                 |
       YES                NO
        |                 |
        v                 v
      Claude        Route per ROUTING_RULES.md
        |           fallback column -> Ollama
        v           (Qwen2.5-Coder / DeepSeek-Coder)
   QUALITY_GUIDELINES.md      |
        |                     v
        v               QUALITY_GUIDELINES.md
      Commit                  |
        |                     v
        v               Mark commit as
       Done            "fallback-authored"
                              |
                              v
                        Commit + flag for
                        Claude review on return
                              |
                              v
                        Resume Claude later
                        (see Recovery below)
```

## Triggering fallback

Fallback applies when Claude Code is unreachable for the duration of the task at hand — outage, rate limit, account/auth issue, or no network path to the Claude API. It is a per-task decision, not a mode switch for the whole project: if Claude becomes available again mid-session, switch back for the next task rather than continuing on a local model out of inertia.

## During fallback

1. Classify the task per [TASK_CLASSIFICATION.md](TASK_CLASSIFICATION.md) as usual.
2. Route to the fallback model named in [ROUTING_RULES.md](ROUTING_RULES.md) for that category. If the task is one [ROUTING_RULES.md](ROUTING_RULES.md) marks as not delegable (e.g. Planning), fallback means: pause that task, continue other delegable work, and resume the non-delegable task when Claude returns — do not force a local model into a role it isn't routed for.
3. Use the matching template in [prompts/](prompts/) and the matching loop in [workflows/ollama.md](workflows/ollama.md).
4. Apply [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md) before committing — the bar does not lower because the model changed.
5. Tag the commit message with `[fallback:<model>]` (e.g. `[fallback:qwen2.5-coder]`) so fallback-authored work is searchable later.
6. If, while working, the task turns out to touch a production directory or require architecture-level reasoning (escalation triggers in [ROUTING_RULES.md](ROUTING_RULES.md)), stop and queue it for Claude rather than finishing it on the fallback model.

## Recovery procedures

When Claude becomes available again:

1. List commits tagged `[fallback:*]` since the last recovery pass (`git log --grep="\[fallback:"`).
2. For each, have Claude review the diff against [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md) as if it were an incoming PR — this is the "second opinion" review rule from [ROUTING_RULES.md](ROUTING_RULES.md) (rule 5), applied specifically to fallback output.
3. Anything that fails review gets corrected by Claude in a follow-up commit, not by rewriting the fallback commit's history.
4. Anything queued during fallback because it required escalation (step 6 above) is now picked up normally.
5. Once review is complete, the `[fallback:*]` tag is informational history — no further action needed.

This keeps fallback usable for continuity without quietly lowering the bar for production-relevant work: local models can keep development moving, but Claude still gets the final say on anything that was originally routed to it.
