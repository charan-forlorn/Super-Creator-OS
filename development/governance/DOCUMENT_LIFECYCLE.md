# Document Lifecycle

> Status: Approved

Every document under `development/` carries a status. This file defines what each status means and how a document moves between them.

## Statuses

```text
  Draft
    |
    v
  Review
    |
    v
  Approved
    |
    v
  Deprecated
    |
    v
  Archived
```

- **Draft** — newly written or substantially rewritten; not yet relied on by any playbook/workflow.
- **Review** — proposed for promotion to Approved; under active scrutiny (see [CHANGE_CONTROL.md](CHANGE_CONTROL.md) for governing documents specifically).
- **Approved** — the current, relied-upon version. Playbooks, workflows, and checklists should only cite Approved documents.
- **Deprecated** — superseded by a newer document but kept for reference/history; nothing should newly cite a Deprecated document.
- **Archived** — retained for historical record only; not linked from any active document.

## How to apply

State the status at the top of a document, e.g.:

```text
> Status: Approved (see governance/DOCUMENT_LIFECYCLE.md)
```

A document moves forward one stage at a time — Draft documents are not cited as authoritative by playbooks/checklists until they reach Approved. Governing documents (`../ai/ROUTING_RULES.md`, `../ai/AI_CAPABILITY_MATRIX.md`, and similar) additionally require [CHANGE_CONTROL.md](CHANGE_CONTROL.md)'s review gate to move from Review to Approved.

## Scope of this introduction

This convention applies going forward from v1.1.1. Retroactively stamping every existing v1.0/v1.1 file with a status is a maintenance pass of its own, not part of this addition — new and substantially-edited documents should adopt it immediately; older documents can be stamped opportunistically as they're next touched.
