# Decision Register (`DD-xxx`)

> **Status:** ACTIVE (Phase 2.5). Each decision is a recorded design or governance choice
> with rationale and supporting Evidence IDs. A decision may be **SUPERSEDED** but never
> deleted or renumbered (per `TRACEABILITY_STANDARD.md`).
>
> **Kind:** `design` = engineering choice in the codebase · `governance` = rule for how
> the project/specs are run · `project` = a scoping decision for this specification effort.

| ID | Decision | Kind | Rationale | Evidence | Status |
|---|---|---|---|---|---|
| DD-001 | **Additive-only discipline** — never edit a core file in place; extend via new optional fields / new modules | design | Keeps existing records and contracts valid by construction; enables safe evolution | EV-038, EV-014 | ACTIVE |
| DD-002 | **Single safe memory write path** — all system-of-record writes go through `safe_append`; nothing else may write the store | design | Atomicity + append-only + tamper-evidence + write-token are only enforceable through one chokepoint | EV-017, EV-039 | ACTIVE |
| DD-003 | **Observed-only telemetry** — predicted metrics are rejected at capture; never substituted for observed | design | Prevents hallucinated learning; preserves trust in the calibration signal | EV-040, EV-028 | ACTIVE |
| DD-004 | **Immutable v1 memory contract** — `V1_REQUIRED` frozen; v2/v3 optional & additive | design | Backward compatibility; a schema-narrowing change cannot be written | EV-041, EV-013, EV-014 | ACTIVE |
| DD-005 | **Heuristic, deterministic analysis** — no ML weights in the core video path | design | Determinism, offline guarantee, verifiability | EV-042, EV-020, EV-004 | ACTIVE |
| DD-006 | **Offline / local-first core path** — no paid APIs, no network for the core pipeline | design + governance | Founder constraint; privacy; reproducibility; cost | EV-004, EV-029 | ACTIVE |
| DD-007 | **Document-driven orchestration** — the orchestrator is a prompt; code modules are CLI tools + importable functions wired by the documented procedure | design | Keeps coordination legible and AI-authorable; avoids a brittle service | EV-006, EV-009 | ACTIVE |
| DD-008 | **Claude directs, tools render** — AI plans/critiques; FFmpeg et al. execute | governance | Quality + control; separates creative judgment from deterministic execution | EV-002 | ACTIVE |
| DD-009 | **Source must live in HEAD** — no capability may be delivered as `.pyc`-only or live only on an unmerged lineage | governance | The current checkout is a non-functional shell for lineage-B modules; this is a defect to be ended | EV-033, EV-034, EV-032 | ACTIVE |
| DD-010 | **Current checkout is truth (spec baseline = `HEAD 6bec9c4`)** — audits are historical evidence of an unmerged lineage; re-verify before asserting as current | project | User-ratified this session; reconciles the lineage divergence honestly | EV-032, EV-033 | ACTIVE |
| DD-011 | **English canonical, Thai preserved in quotes** — all spec/EKB docs in English; original Thai source wording quoted where it is source-of-truth | project | Tooling + AI-agent + contributor accessibility; fidelity to the founder's wording | EV-001, EV-002 | ACTIVE |
| DD-012 | **Maturity expressed as L0–L5, assessed as-of-HEAD**, with an A/B/C→L mapping retained additively | governance | One consistent maturity scheme that tells the truth about the delivered tree | EV-032, EV-033 | ACTIVE |
| DD-013 | **Bounded growth required** — every append-only store must have retention/rotation; appends must trend O(1) amortized | design | Prevents unbounded local-disk and super-linear write cost at scale | EV-043, EV-044 | ACTIVE |
| DD-014 | **No `eval`, no `shell=True`, list-form subprocess, narrow self-created deletes** | design | Local single-user security soundness; remove the one `eval` sink | EV-046, EV-029 | ACTIVE |

**Total: 14 decisions.** design=8, governance=4, project=3 (DD overlaps kinds where noted).
Every decision cites ≥1 Evidence ID. ✓
