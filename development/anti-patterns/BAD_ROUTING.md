# Anti-pattern — Bad Routing

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

What not to do, contrasted with [../checklists/MODEL_SELECTION.md](../checklists/MODEL_SELECTION.md) and [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md).

## Bad example 1 — routing by feel

> "This refactor touches `scos/learning/learning_coordinator.py`, but it's just renaming a variable, so I'll let Qwen2.5-Coder handle it without escalating."

### Why this is bad

`scos/learning/` is a production directory. [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md)'s decision rule 1 routes any production-directory change to Claude regardless of how "simple" it looks — the rule exists precisely because "simple" is a judgment call that's wrong often enough to not be trusted as a routing input. This is the exact failure mode [../playbooks/REFACTOR_MODULE.md](../playbooks/REFACTOR_MODULE.md) step 2 is designed to catch.

## Bad example 2 — changing routing without evidence

> "I think Claude is overkill for documentation now, let's route all documentation to Qwen2.5-Coder instead of DeepSeek-Coder because it feels faster."

### Why this is bad

This is a governing-document change (to [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md)) made on impression, with no benchmark data or evaluation score behind it. It skips the evidence chain required by [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md): Capability Matrix update ← Benchmark data ← Evaluation score ← Approve.

## The fix

Use the decision tree in [../checklists/MODEL_SELECTION.md](../checklists/MODEL_SELECTION.md) for routing a single task — it resolves example 1 immediately (production directory → Claude). For changing routing policy itself, follow [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md)'s full evidence chain, recording real runs via [../playbooks/MODEL_COMPARISON.md](../playbooks/MODEL_COMPARISON.md) first.
