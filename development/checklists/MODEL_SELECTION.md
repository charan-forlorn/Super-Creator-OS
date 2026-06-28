# Checklist — Model Selection

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

The fast path for routing a task: follow the decision tree below. It covers every category in [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md). Full prose rules and escalation logic live in [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) — read that if a branch below doesn't resolve cleanly.

## Decision tree

```text
Does the task touch a production directory
(scos/, source/, memory/, assets/, analytics/,
 rendering/, workflow/, tests/) or change
runtime behavior?
        |
       YES -----------------------------------> Claude
        |
        NO
        |
        v
Need Architecture (cross-module design)?
        |
       YES -----------------------------------> Claude
        |
        NO
        |
        v
Need Planning (full project context)?
        |
       YES -----------------------------------> Claude
        |
        NO
        |
        v
Need Repository Analysis / large reasoning
across many files?
        |
       YES -----------------------------------> Claude
        |
        NO
        |
        v
Need Review (judgment on a diff/PR)?
        |
       YES -----------------------------------> Claude (primary),
        |                                       second-opinion model differs
        NO
        |
        v
Need Debugging (non-production)?
        |
       YES -----------------------------------> Ollama (DeepSeek-Coder)
        |
        NO
        |
        v
Need Unit Test?
        |
       YES -----------------------------------> Ollama (Qwen2.5-Coder)
        |
        NO
        |
        v
Need Refactor (non-production)?
        |
       YES -----------------------------------> Ollama (Qwen2.5-Coder)
        |
        NO
        |
        v
Need Documentation?
        |
       YES -----------------------------------> Ollama (DeepSeek-Coder)
        |
        NO
        |
        v
Need Research (exploratory, cheap to redo)?
        |
       YES -----------------------------------> Ollama (any available)
        |
        NO
        |
        v
None of the above resolved it -----------------> Claude (default —
                                                   ambiguity itself is
                                                   a signal per
                                                   ROUTING_RULES.md rule 6)
```

## Final sanity-check checklist

- [ ] Tree branch followed matches the task's actual classification in [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md)
- [ ] No escalation trigger from [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) was missed (production touch, architecture-level reasoning discovered mid-task)
- [ ] If this is a second-opinion review, the reviewing model differs from the authoring model

See [../anti-patterns/BAD_ROUTING.md](../anti-patterns/BAD_ROUTING.md) for examples of routing decisions made by feel instead of by this tree.
