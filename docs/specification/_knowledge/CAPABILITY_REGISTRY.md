# Capability Registry

> **Status:** ACTIVE (Phase 2.8). The **governance record** for every capability —
> enriches `CAPABILITY_INVENTORY.md` (the spine) with owner, dependencies, consumers,
> current/target maturity (per `MATURITY_MODEL.md`), and related risks. Maturity is
> **as-of-`HEAD 6bec9c4`**. `[hist:Lx]` = maturity reached on the unmerged lineage
> (informational; does not raise the as-of-HEAD level — EV-033, DD-009).
>
> **Owner roles** (this is a single-maintainer project today; "owner" = the role
> accountable for the capability): *Engine* (video execution), *Learning* (knowledge
> layer), *Skills* (prompt/director layer), *Platform* (orchestration/infra), *Memory*
> (system-of-record). All currently held by the project maintainer.

---

## 1. Registry

| CAP | Name | Owner | Cur. | Target | Evidence / Decisions | Depends on | Consumed by | Key risk |
|---|---|---|---|---|---|---|---|---|
| CAP-001 | Brief & reference intake | Platform | L2 | L4 | EV-010, EV-001 | CAP-014, CAP-015 | CAP-023 | unjoinable records (EV-026) |
| CAP-002 | Asset analysis | Engine | L2 | L4 | EV-018, EV-020 | CAP-020 | CAP-003, CAP-006 | semantic labels need detector (EV-023) |
| CAP-003 | Highlight detection (WF-1) | Engine | L2 `[hist:L4]` | L4 | EV-020, DD-005 | CAP-002 | CAP-004, CAP-007 | source not in HEAD (EV-033) |
| CAP-004 | Narrative extraction (WF-1) | Engine | L2 `[hist:L4]` | L4 | EV-021, DD-005 | CAP-003 | CAP-007, CAP-008 | source not in HEAD (EV-033) |
| CAP-005 | Story arc planning | Skills | L3 | L4 | EV-012, EV-003 | CAP-001 | CAP-006 | prompt unverified by test |
| CAP-006 | Timeline / EDL editing | Skills | L3 | L4 | EV-054, EV-012 | CAP-005, CAP-002 | CAP-007, CAP-009 | adapter writer untested (EV-050) |
| CAP-007 | Short generation (WF-2) | Engine | L2 `[hist:L4]` | L5 | EV-022, DD-005 | CAP-004, CAP-006 | CAP-013 | source not in HEAD; Windows fonts |
| CAP-008 | Music montage (WF-2) | Engine | L2 `[hist:L4]` | L4 | EV-022 | CAP-004 | CAP-013 | multi-encode cost; not in HEAD |
| CAP-009 | Color grading | Engine | L3 | L4 | EV-018, EV-019 | CAP-020 | CAP-013 | MCP `eval` sink (EV-046) |
| CAP-010 | Subtitle / captions | Engine | L3 | L4 | EV-018, EV-019 | CAP-020 | CAP-013 | font portability (EV-047) |
| CAP-011 | Retention risk analysis | Skills | L3 | L4 | EV-012, EV-003 | CAP-005 | CAP-012, CAP-014 | scores are human-supplied (EV-040) |
| CAP-012 | QA review (Pass/Fail) | Skills | L3 | L4 | EV-012 | CAP-011 | CAP-013 | prompt unverified by test |
| CAP-013 | Multi-platform export | Skills | L2 | L4 | EV-012, EV-009 | CAP-007, CAP-009, CAP-010 | CAP-023 | platform presets unverified |
| CAP-014 | Memory store (safe write) | Memory | L2 `[hist:L5]` | L5 | EV-017, DD-002 | — | CAP-001, CAP-015 | **spine not in HEAD** (EV-033); O(n²)/unbounded (EV-043/044) |
| CAP-015 | Memory recall / recommendation | Learning | L2 `[hist:L3]` | L4 | EV-024, DD-007 | CAP-014 | CAP-001 | reuses predicted not calibrated (EV-025) |
| CAP-016 | Telemetry capture (observed) | Learning | L2 `[hist:L4]` | L4 | EV-040, DD-003 | CAP-014 | CAP-017 | 0 observed rows (EV-027); not in HEAD |
| CAP-017 | Learning evaluation / calibration | Learning | L2 `[hist:L4]` | L4 | EV-024, EV-025 | CAP-016 | CAP-018 | output consumed by nobody (EV-025) |
| CAP-018 | **Learning loop closure** | Learning | L1 | L5 | EV-025, EV-026 | CAP-015, CAP-017 | CAP-001 | the open seam (L1/L2 breaks) |
| CAP-019 | MCP tool surface | Engine | L2 `[hist:L3]` | L4 | EV-019, EV-046 | CAP-020 | external clients | `eval` (EV-046); no allow-list (EV-048) |
| CAP-020 | Video engine (video-use) | Engine | L3 | L5 | EV-018, DD-006 | numpy/ffmpeg | CAP-002/009/010 | no dedicated tests in HEAD (EV-049) |
| CAP-021 | Event audit spine | Platform | L2 `[hist:L4]` | L4 | EV-007, EV-024 | — | CAP-022 | unbounded `events.jsonl` (EV-044) |
| CAP-022 | Data quality reporting | Learning | L2 `[hist:L4]` | L4 | EV-049, EV-040 | CAP-014, CAP-016 | maintainer | not in HEAD (EV-033) |
| CAP-023 | Orchestration (15-step) | Platform | L3 | L4 | EV-009, DD-007 | all skills | the operator | prompt-only; no code guards (EV-046/S2) |

## 2. Validation against the model

- ✓ **Every capability has an owner** (Engine/Learning/Skills/Platform/Memory).
- ✓ **Every capability cites ≥1 Evidence ID** and has **exactly one** current L-level.
- ✓ **Every capability has a target** maturity.
- ✓ **No orphan capabilities** — each has ≥1 consumer (or an external consumer / the maintainer).
- ✓ Dependencies reference only defined `CAP` IDs (or named externals numpy/ffmpeg).

## 3. Roll-up

| Owner | Caps | Notable gap |
|---|---|---|
| Engine | 8 | 4 are lineage-B (`.pyc`-only in HEAD) |
| Learning | 5 | loop open (CAP-018 L1); spine modules not in HEAD |
| Skills | 5 | all L3 prompts, none test-verified (no L4) |
| Platform | 3 | orchestration prompt-only |
| Memory | 1 | the hardened store is **L2 in HEAD** (its strength is unmerged) |

**Highest-leverage targets:** restore lineage-B source into HEAD (raises CAP-003/004/007/
008/014/016/017/019/021/022 from L2 toward their `[hist]` levels) and close CAP-018
(L1→). Both are recorded in the roadmap and Phase 2.9 backlog.
