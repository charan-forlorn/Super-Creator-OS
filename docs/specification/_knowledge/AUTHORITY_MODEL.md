# Authority Model

> **Status:** ACTIVE (Phase 2.8). Defines the **layer hierarchy** of the knowledge system:
> who *defines*, who *validates*, and who *may change* whom. This resolves precedence when
> documents disagree. Evidence: the project's own discipline (DD-001, DD-006, DD-007,
> DD-009, DD-010) and the founder vision (EV-001, EV-035).

---

## 1. The hierarchy

```
            ┌─────────────────────────────┐
   STRATEGY │ 1. VISION                    │  source/_Super Creator OS V.1.md
            └──────────────┬──────────────┘
                           ▼
 GOVERNANCE  │ 2. PROJECT CONSTITUTION      │  docs/specification/PROJECT_CONSTITUTION.md
            └──────────────┬──────────────┘
                           ▼
            ┌─────────────────────────────┐
   INTENT   │ 3. SPECIFICATION             │  docs/specification/*.md  (+ EKB substrate)
            └──────────────┬──────────────┘
                           ▼
   DESIGN   │ 4. ARCHITECTURE              │  (future; project_audit/architecture_audit.md = current evidence)
                           ▼
   RULES    │ 5. STANDARDS                 │  coding/testing/deployment standards (future)
                           ▼
  BUILD     │ 6. IMPLEMENTATION            │  integrations/**, skills/**, memory/**  ← REPOSITORY TRUTH
                           ▼
  PROOF     │ 7. TESTING                   │  tests/** , CI (future)
                           ▼
  RELEASE   │ 8. DEPLOYMENT                │  runtime/provisioning (future)
                           ▼
  RUN       │ 9. OPERATIONS                │  telemetry, retention, ops runbooks (future)
```

The **Engineering Knowledge Base** (`_knowledge/`) and **Evidence Ledger** (`_evidence/`)
are not a layer in this stack; they are the **evidentiary substrate beside layer 3** that
binds every layer to repository facts via `EV`/`DD`/`CAP` IDs.

## 2. Defines / Validates / May-change matrix

| Layer | Defines (sets intent for) | Validated by | May be changed by | Stability |
|---|---|---|---|---|
| 1 Vision | everything below | the founder | the founder only | very high |
| 2 Constitution | layers 3–9 governance | Vision + repository evidence | explicit amendment (Constitution §14) | very high |
| 3 Specification | layers 4–9 intent | Constitution + Evidence (EV) | spec author, within Constitution | high |
| 4 Architecture | layers 5–6 structure | Specification + Evidence | architect, within Spec | medium |
| 5 Standards | layer 6–8 rules | Architecture + Constitution | standards owner | medium |
| 6 Implementation | the running truth | Testing + Specification | engineers (additively, DD-001) | low (changes often) |
| 7 Testing | pass/fail truth | Standards | engineers | low |
| 8 Deployment | release facts | Testing | release owner | low |
| 9 Operations | runtime facts | Deployment | operators | low |

## 3. Precedence rules (conflict resolution)

1. **Repository evidence wins over any document** about *what currently is* (DD-010).
   Implementation (layer 6) is the truth of the present; if a spec claims a module exists
   and the repo shows `.pyc`-only (EV-033), the repo is right and the spec is corrected.
2. **Higher layers win over lower layers** about *what should be*. Vision overrides
   Constitution-intent disputes; Constitution overrides Specification; etc.
3. **Two truths, never confused:** Vision = *strategic* truth (what we are building and
   why); Repository = *implementation* truth (what exists now); Constitution = *governance*
   truth (the rules). A lower layer may **report** reality up, but may **not** rewrite a
   higher layer's intent (the anti-pattern: deriving a principle from a temporary
   implementation detail — forbidden by the Constitution).
4. **Within a layer**, the most recently ratified document wins; superseded items are
   marked, never deleted.

## 4. Who may promote a document's status

Status flow (formalized later in Phase 2.9 `DOCUMENT_LIFECYCLE.md`): `PLACEHOLDER →
DRAFT → RATIFIED → SUPERSEDED`. Until then: a spec doc becomes RATIFIED only when it (a)
cites evidence per `TRACEABILITY_STANDARD.md`, (b) does not contradict the Constitution,
and (c) is reviewed by the user. The EKB registers are RATIFIED on creation because they
are pure evidence/decision indexes, correctable by the repository at any time.

## 5. Placement of every current document

| Document | Layer | Authority |
|---|---|---|
| `source/_Super Creator OS V.1.md` | 1 Vision | strategic truth |
| `PROJECT_CONSTITUTION.md` | 2 Constitution | governance truth (placeholder until Phase 3) |
| `SYSTEM_SPEC`, `PRODUCT_SPEC`, `DESIGN_PRINCIPLES`, `DOMAIN_MODEL`, `QUALITY_ATTRIBUTES`, `NON_FUNCTIONAL_REQUIREMENTS`, `SUCCESS_CRITERIA`, `DECISION_PRINCIPLES`, `ROADMAP`, `TERMINOLOGY` | 3 Specification | intent (placeholders) |
| `project_audit/*.md` | evidence for 4 Architecture | read-only audit evidence |
| `_evidence/EVIDENCE_LEDGER.md`, `_knowledge/*` | substrate beside 3 | evidence/index (RATIFIED) |
| `integrations/**`, `skills/**`, `memory/**` | 6 Implementation | repository truth |

Every document is now placed in the hierarchy with a stated authority. ✓
