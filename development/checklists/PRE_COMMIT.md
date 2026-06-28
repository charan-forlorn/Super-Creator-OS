# Checklist — Pre-Commit

> Status: Approved (see [../governance/DOCUMENT_LIFECYCLE.md](../governance/DOCUMENT_LIFECYCLE.md))

- [ ] All items in [../ai/QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md)'s validation checklist satisfied
- [ ] Tests pass (existing suite for the affected area shows zero regressions)
- [ ] No unintended production-directory diff (only the directories explicitly named in the task are touched)
- [ ] No new dependency, runtime, or configuration change outside task scope
- [ ] `[fallback:<model>]` tag applied if this work was done during a Claude-unavailable fallback (see [../ai/FALLBACK_WORKFLOW.md](../ai/FALLBACK_WORKFLOW.md))
- [ ] Commit message describes the change's "why," not just the "what"
