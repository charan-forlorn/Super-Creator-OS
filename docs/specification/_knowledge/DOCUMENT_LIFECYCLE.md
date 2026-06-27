# Document Lifecycle

> **Status:** ACTIVE (Phase 2.9.6). The state machine every knowledge/spec document moves
> through, with transition rules, ownership, and approval authority. Reconciles the status
> labels already in use (`PLACEHOLDER`, `RATIFIED`, `ACTIVE`) into one model. Governance:
> `AUTHORITY_MODEL.md`.

---

## 1. States

```
Draft → Review → Approved → Implemented → Deprecated → Archived
                                   │
                                   └──(superseded)──► (new Draft)
```

| State | Meaning | Existing labels it absorbs |
|---|---|---|
| **Draft** | Authored, not yet reviewed | `PLACEHOLDER` (empty draft), in-progress |
| **Review** | Under review against Constitution + traceability | — |
| **Approved** | Reviewed & accepted; authoritative for its layer | `RATIFIED` |
| **Implemented** | Its intent is realized in the repository (specs whose code exists in HEAD) | `ACTIVE` (for EKB infra docs that are "in force") |
| **Deprecated** | Superseded but kept for reference | `SUPERSEDED` |
| **Archived** | Retired from active use; history only | — |

> Mapping note: EKB infrastructure docs (registers, standards, models) are created
> **Approved/Implemented** because they are pure evidence/governance instruments,
> correctable by the repository at any time (`AUTHORITY_MODEL.md` §4). The 11 spec docs are
> currently **Draft (PLACEHOLDER)**.

## 2. Transition rules

| Transition | Entry criteria | Who authorizes |
|---|---|---|
| Draft → Review | Content complete; cites `EV`/`DD`/`CAP` (`TRACEABILITY_STANDARD.md`) | author |
| Review → Approved | No contradiction with Constitution; traceability check passes; user review | approval authority (see §3) |
| Approved → Implemented | Referenced capability/code present in HEAD (verify per `REPOSITORY_INTELLIGENCE.md`) | owner |
| any → Deprecated | A superseding doc is Approved; `SUPERSEDED-BY` recorded | owner + approver |
| Deprecated → Archived | No longer referenced by active docs | owner |
| Implemented → Review | Repository evidence contradicts the doc (evidence wins, DD-010) | anyone may flag; owner re-opens |

**Append-only history:** transitions never delete content; `Deprecated`/`Archived` docs and
all `EV`/`DD`/`CAP` IDs are retained (`TRACEABILITY_STANDARD.md` §2).

## 3. Ownership & approval authority

| Layer (AUTHORITY_MODEL) | Document owner | Approval authority |
|---|---|---|
| Vision | founder | founder |
| Constitution | maintainer | founder + explicit amendment |
| Specification | spec author | maintainer (user review) |
| EKB (`_knowledge/`, `_repository_model/`) | Platform role | maintainer |
| Architecture/Standards (future) | architect/standards owner | maintainer |
| Implementation/Testing/Deployment/Ops | engineers/operators | maintainer |

(Single-maintainer project today; roles are accountability labels, all currently the
project maintainer — consistent with `CAPABILITY_REGISTRY.md`.)

## 4. Current lifecycle state of every document

| Document(s) | State |
|---|---|
| `source/_Super Creator OS V.1.md` | Approved (Vision) |
| `_evidence/EVIDENCE_LEDGER.md`, all `_knowledge/*`, `_repository_model/*` | Approved/Implemented (in force) |
| `PROJECT_CONSTITUTION.md` | Draft (PLACEHOLDER) — Phase 3 |
| 10 other spec docs (`SYSTEM_SPEC`…`ROADMAP`, `TERMINOLOGY`) | Draft (PLACEHOLDER) |
| `project_audit/*.md` | Approved (read-only evidence; historical) |

## 5. Review cadence

- EKB registers: re-validated whenever the repository changes a cited path (event-driven),
  and at the start of each new phase.
- Spec docs: reviewed at authoring (Phase 3+) and whenever a governing higher-layer doc
  changes.
- Stale `A`-basis evidence: re-verify per `KNOWLEDGE_RETRIEVAL.md` §5 before reuse.
