# Maturity Model (L0–L5)

> **Status:** ACTIVE (Phase 2.8). The **single** capability-readiness scale for Super
> Creator OS. Replaces the interim A/B/C tagging used in the Evidence Ledger (an A/B/C→L
> mapping is provided so no prior tagging is lost — DD-012). Maturity is always assessed
> **as of `HEAD`** (the delivered tree), per DD-010.

---

## 1. The levels

| Level | Name | A capability is here when… | Evidence required to claim it |
|---|---|---|---|
| **L0** | Vision | It is named as desired in the Vision/roadmap, nothing built | A roadmap/vision reference (EV) |
| **L1** | Specified | Its intent is written in a ratified spec doc | Spec section citing EV/DD |
| **L2** | Architected | A design exists (and may have a reference implementation **outside HEAD**) but it is **not runnable from HEAD** | Architecture/audit evidence; `[hist:…]` note if code is only in unmerged history |
| **L3** | Implemented | Source is **present in HEAD** and importable/invokable; no verifying test yet | File path in HEAD + manual invocation |
| **L4** | Verified | ≥1 passing **runtime** test on the pinned runtime (CPython 3.11); for video, a passing smoke render producing an output file | Test result / CI evidence |
| **L5** | Production Ready | A non-author can run it end-to-end on a clean machine and trust it: deps from a committed manifest, bounded growth, no machine-specific paths, loop closed where applicable | Full Definition-of-Production-Ready (Constitution §7) |

**Advancement is monotonic and evidence-gated:** a capability may not be tagged at a level
without the evidence that level requires. Absence of source in HEAD **caps** a capability
at L2 regardless of how mature its unmerged implementation is (this is the lineage-B
hazard — EV-033, DD-009).

## 2. A/B/C → L mapping (additive; nothing lost)

The Evidence Ledger §0 classified capabilities as A/B/C. That tagging is preserved in the
ledger; this table is the canonical translation going forward.

| Old | Old meaning | Maps to | Notes |
|---|---|---|---|
| **A** | Present & runnable now (HEAD) | **L3**, or **L4** if a runtime test exists | video-use engine, skills-as-prompts, timeline_to_edl |
| **B** | In history, not in HEAD (orphaned `.pyc`) | **L2** with `[hist:L4/L5]` | learning spine, WF-1/2, MCP, render_to_memory |
| **C** | Planned / unbuilt | **L0** (vision) or **L1** (if specified) | browser control, full autonomy |

## 3. Current distribution (from `CAPABILITY_INVENTORY.md`, as-of-HEAD)

| Level | Count | Capabilities |
|---|---|---|
| L0 | 0 | — |
| L1 | 1 | CAP-018 (learning loop closure) |
| L2 | 13 | CAP-001/002/003/004/007/008/013/014/015/016/017/019/021/022 (subset; many `[hist:…]`) |
| L3 | 9 | CAP-005/006/009/010/011/012/020/023 (+CAP-002 borderline) |
| L4 | 0 | — (no runtime tests pass from HEAD today) |
| L5 | 0 | — |

> **Headline:** **nothing is L4+ from the current checkout.** The project's praised
> "production-ready memory spine" (88–90/100 on the audited lineage) is **L2 in HEAD**
> because its source is not checked out (EV-033). This is the single most important
> maturity fact and the first target of the roadmap.

## 4. Maturity vs the Constitution's "Production Ready"

L5 == Constitution §7 *Definition of Production Ready*. L4 == has runtime proof but not yet
clean-machine/bounded/closed-loop complete. Do not call anything "production" below L5.

## 5. How to record maturity

Each capability carries **exactly one** current L-level in `CAPABILITY_REGISTRY.md`, plus a
**target** L-level. The `[hist:Lx]` annotation records the maturity its implementation
reached on an unmerged lineage — informational only; it never raises the as-of-HEAD level.
