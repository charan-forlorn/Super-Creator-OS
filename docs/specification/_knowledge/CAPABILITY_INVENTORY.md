# Capability Inventory (`CAP-xxx`)

> **Status:** ACTIVE (Phase 2.5). The capability **spine** — atoms only (id, name,
> one-line, primary evidence/decision, provisional maturity). The full governance record
> (owner, dependencies, consumers, target maturity, risks, exact maturity justification)
> lives in `CAPABILITY_REGISTRY.md` (Phase 2.8), which this inventory seeds.
>
> **Provisional maturity** uses the L0–L5 scale defined in `MATURITY_MODEL.md` (Phase 2.8),
> assessed **as of `HEAD 6bec9c4`**. `[hist:L4]` means a reference implementation exists on
> the unmerged `h1-foundation` lineage but is **not** in the current checkout (see EV-033).

| ID | Capability | One-line | Primary EV/DD | Prov. maturity |
|---|---|---|---|---|
| CAP-001 | Brief & reference intake | Receive a brief and recall the nearest-niche prior project from memory | EV-010, EV-001 | L2 |
| CAP-002 | Asset analysis | Inspect/ingest source media (ffprobe metadata, energy/motion) | EV-018, EV-020 | L2 |
| CAP-003 | Highlight detection (WF-1) | Fuse audio RMS + motion + onset → highlight candidates | EV-020, DD-005 | L2 `[hist:L4]` |
| CAP-004 | Narrative/story extraction (WF-1) | Detect buildup→climax→resolution episodes with arc scoring | EV-021, DD-005 | L2 `[hist:L4]` |
| CAP-005 | Story arc planning | Director-level emotional arc / scene order / hooks (skill prompt) | EV-012, EV-003 | L3 |
| CAP-006 | Timeline / EDL editing | Turn a story arc into a production timeline / EDL | EV-054, EV-012 | L3 |
| CAP-007 | Short generation (WF-2) | Single-pass 9:16 short with hook overlay + loudnorm | EV-022, DD-005 | L2 `[hist:L4]` |
| CAP-008 | Music montage / 60s hype (WF-2) | Beat-synced montage, reframe, ducking, FX | EV-022 | L2 `[hist:L4]` |
| CAP-009 | Color grading | Apply look/grade presets to footage | EV-018, EV-019 | L3 |
| CAP-010 | Subtitle / caption generation | Transcribe + burn/format subtitles | EV-018, EV-019 | L3 |
| CAP-011 | Retention risk analysis | Score hook/pacing/emotion/payoff; flag drop-off risk (skill) | EV-012, EV-003 | L3 |
| CAP-012 | QA review (Pass/Fail) | Final pre-export quality gate (skill checklist) | EV-012 | L3 |
| CAP-013 | Multi-platform export | Export TikTok / IG Reel / IG Story variants (skill) | EV-012, EV-009 | L2 |
| CAP-014 | Memory store (safe write) | Append a project record through the single hardened write path | EV-017, DD-002 | L2 `[hist:L5]` |
| CAP-015 | Memory recall / recommendation | Produce a creative seed from nearest-niche prior record | EV-024, DD-007 | L2 `[hist:L3]` |
| CAP-016 | Telemetry capture (observed) | Record observed platform metrics, predicted rejected | EV-040, DD-003 | L2 `[hist:L4]` |
| CAP-017 | Learning evaluation / calibration | Compute mae/bias/observed_benchmark per niche | EV-024, EV-025 | L2 `[hist:L4]` |
| CAP-018 | Learning loop closure | Feed calibrated benchmark + provenance back into decisions | EV-025, EV-026 | L1 |
| CAP-019 | MCP tool surface | 11 ffmpeg-backed FastMCP tools for video ops | EV-019, EV-046 | L2 `[hist:L3]` |
| CAP-020 | Video engine (video-use) | Conversation-driven render/grade/transcribe helper engine | EV-018, DD-006 | L3 |
| CAP-021 | Event audit spine | Append-only JSONL audit log of loop events | EV-007, EV-024 | L2 `[hist:L4]` |
| CAP-022 | Data quality reporting | DQ checks over records + telemetry | EV-049, EV-040 | L2 `[hist:L4]` |
| CAP-023 | Orchestration (15-step) | Coordinate all skills through the documented pipeline | EV-009, DD-007 | L3 |

**Total: 23 capabilities.** Provisional maturity (as-of-HEAD): L1=1, L2=13, L3=9, L4=0,
L5=0. Twelve carry a `[hist:…]` annotation (reference implementation on the unmerged
lineage — the central gap captured by DD-009). Every capability cites ≥1 `EV`. ✓
