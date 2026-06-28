# Template — Change Request

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

The shape a [../playbooks/](../playbooks/) procedure points to before any implementation starts, especially [../playbooks/REFACTOR_MODULE.md](../playbooks/REFACTOR_MODULE.md). For changes to a *governing document itself* (e.g. `../ai/ROUTING_RULES.md`), use [../governance/CHANGE_CONTROL.md](../governance/CHANGE_CONTROL.md) instead — this template is for code/doc changes in general, not layer-governance changes.

---

**What's changing:** `<exact description>`

**Why:** `<motivation — bug, tech debt, new requirement>`

**Blast radius:** `<files/modules affected, and anything downstream of them>`

**Production directory flag:** `<yes/no — see ../ai/ROUTING_RULES.md's production-touch rule>`

**Rollback plan:** `<how to revert if this turns out to be wrong — e.g. "single commit, revertable cleanly">`

**Routed model:** `<per ../ai/ROUTING_RULES.md>`
