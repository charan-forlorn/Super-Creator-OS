# Template — Task

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

Generic task definition shape. The general-purpose parent that [../playbooks/](../playbooks/) procedures instantiate per scenario.

---

**Task category:** `<one of: Architecture, Implementation, Testing, Review, Debugging, Documentation, Refactoring, Planning, Research — see [../ai/TASK_CLASSIFICATION.md](../ai/TASK_CLASSIFICATION.md)>`

**Routed model:** `<look up in ../ai/ROUTING_RULES.md, confirm against ../checklists/MODEL_SELECTION.md>`

**Scope:**
- Files/directories in play: `<exact paths>`
- Production directories touched (if any): `<name explicitly, or "none">`

**Constraints:**
- `<hard limits — no new dependency, no API change, must stay deterministic, etc.>`

**Acceptance bar:**
- `<what "done" looks like — tests passing, doc complete, etc.>`

**Pre-implementation check:** [../checklists/PRE_IMPLEMENTATION.md](../checklists/PRE_IMPLEMENTATION.md)
