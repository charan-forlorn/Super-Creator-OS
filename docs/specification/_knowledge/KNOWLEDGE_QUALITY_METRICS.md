# Knowledge Quality Metrics

> **Status:** ACTIVE (Phase 2.8). Measurable health of the Engineering Knowledge Base.
> All counts verified by `grep` on 2026-06-27 against `HEAD 6bec9c4`. Each metric states
> its **computation method** so it can be recomputed deterministically.

---

## 1. Scorecard

| Metric | Value | Method |
|---|---|---|
| **Traceability Coverage** | **100%** | (`CAP` citing ≥1 `EV`/`DD`)/(all `CAP`) = 23/23; (`DD` citing ≥1 `EV`)/(all `DD`) = 14/14 |
| **Reference Integrity** | **100%** (IDs) | referenced `EV` IDs that resolve to a register row = 55/55 (`comm -23` empty) |
| **Knowledge Completeness — infrastructure** | **100%** | `_knowledge/` + `_evidence/` docs authored = 16/16 planned |
| **Knowledge Completeness — specification** | **0%** (by design) | populated spec docs = 0/11 (content is Phases 3–13) |
| **Duplicate Ratio** | **~0%** (controlled) | uncontrolled duplicate definitions = 0; 2 *controlled* pairs (ledger↔register; glossary↔terminology) each with an explicit "source vs view" link |
| **Evidence Freshness** | **34.5%** live | live-verified (`V`)/(all `EV`) = 19/55; remaining 36 are audit-sourced (`A`) and stale-risk |
| **Decision Coverage** | **100%** | `DD` with ≥1 `EV` citation = 14/14 |
| **Capability Coverage** | **100%** | `CAP` with owner + ≥1 `EV` + exactly one maturity level = 23/23 |
| **Documentation Consistency** | **~95%** | naming 100% (`UPPER_SNAKE_CASE`); terminology single-source 100%; minus minor heading/emphasis drift in pre-existing placeholders |

## 2. Interpretation

- **The traceability spine is solid (100%).** Every capability and decision is grounded in
  evidence, and every evidence reference resolves. This is the core success criterion of
  Phase 2.5–2.8 and it is met.
- **The dominant weakness is Evidence Freshness (34.5% live).** Nearly two-thirds of
  evidence is inherited from the 2026-06-22 audits of an unmerged lineage. Per
  `REPOSITORY_INTELLIGENCE.md` §6, any `A`-basis claim about the learning spine / WF / MCP
  must be re-verified against HEAD before being treated as current.
- **Specification completeness is 0% by design** — the spec layer is intentionally empty
  until Phase 3+. This is not a defect; it is the next body of work.

## 3. Trend targets (for the next pass)

| Metric | Now | Target after Phase 3+ | Target after lineage restore (DD-009) |
|---|---|---|---|
| Evidence Freshness | 34.5% | 50% | ≥ 80% live |
| Spec Completeness | 0% | ≥ 80% | 100% |
| Capability maturity ≥ L4 | 0/23 | n/a | ≥ 10/23 |
| Traceability Coverage | 100% | 100% (hold) | 100% (hold) |

## 4. Recomputation

```
EV defined : grep -oE 'EV-[0-9]{3}' _knowledge/EVIDENCE_REGISTER.md | sort -u | wc -l
EV resolved: comm -23 <(referenced) <(defined)            # must be empty
freshness  : grep -cE '\| V \|$' EVIDENCE_REGISTER.md  /  total rows
DD coverage: every DD row contains an EV- token
CAP coverage: every CAP row in registry has owner + EV + one L-level
```

These commands are the canonical source of the numbers above; re-run to refresh.
