# Knowledge Graph

> **Status:** ACTIVE (Phase 2.8). The unified node/edge view of the system's knowledge.
> A machine-readable serialization (`knowledge.graph.json`) is deferred to Phase 2.9.
> Edges use a controlled vocabulary: **owns, defines, validates, depends-on, produces,
> consumes, reads, writes, governs, implements**.

---

## 1. Node types

| Type | Examples | Source |
|---|---|---|
| Document | Vision, Constitution, spec docs, EKB docs | `AUTHORITY_MODEL.md` |
| Capability | CAP-001…CAP-023 | `CAPABILITY_REGISTRY.md` |
| Agent/Skill | orchestrator, storytelling, video-editor, qa-reviewer, retention-expert, social-media-manager | EV-012 |
| Workflow | 15-step pipeline; WF-1; WF-2; WF-3 | EV-009, EV-011 |
| Memory | database.json, telemetry.json, schemas, backups | EV-013–EV-017 |
| Pipeline/Engine | video-use engine; ffmpeg render path | EV-018 |
| External system | FFmpeg, Remotion, CapCut, DaVinci, ElevenLabs Scribe | EV-002, EV-014 |
| MCP | scos_video_mcp (11 tools) | EV-019 |
| Database | memory store (system-of-record) | EV-013 |
| AI provider | Claude (director/creative reasoning) | EV-002 |
| Repository | HEAD lineage; h1-foundation lineage | EV-032 |

## 2. Core graph (subsystems & flow)

```mermaid
flowchart TD
  subgraph AIlayer[AI / Director]
    CLAUDE[Claude — Creative Director]
    ORC[Orchestrator skill]
    SK[5 role skills]
  end
  subgraph Exec[Execution layer · ffmpeg+numpy]
    VU[video-use engine CAP-020]
    WF1[WF-1 highlight+narrative CAP-003/004]
    WF2[WF-2 short+montage CAP-007/008]
    MCP[MCP surface CAP-019]
  end
  subgraph Learn[Learning layer · stdlib]
    REC[recommendation CAP-015]
    TEL[telemetry capture CAP-016]
    EVAL[evaluator/calibration CAP-017]
    LOOP[loop closure CAP-018]
    EVT[event spine CAP-021]
    DQ[data quality CAP-022]
  end
  subgraph Mem[Memory · system-of-record]
    DB[(database.json)]
    TJ[(telemetry.json — absent EV-016)]
    WR[safe write path CAP-014]
  end
  EXT[FFmpeg/Remotion/CapCut/DaVinci]

  CLAUDE --> ORC --> SK
  ORC -->|reads| DB
  ORC --> WF1 --> WF2 --> VU --> EXT
  SK -->|direct| WF1 & WF2
  REC -->|reads| DB
  ORC --> REC
  WF2 --> WR --> DB
  TEL --> WR --> TJ
  DB & TJ --> EVAL --> LOOP
  LOOP -.intended, broken.-x REC
  EVT -->|audit| DQ
  MCP --> EXT
  VU --> MCP
```

The dashed broken edge **LOOP ⇏ REC** is the open learning seam (EV-025, CAP-018).

## 3. Document ↔ capability ownership (selected edges)

```mermaid
flowchart LR
  CAPR[CAPABILITY_REGISTRY] -- governs --> CAPS((CAP-001..023))
  EVR[EVIDENCE_REGISTER] -- supports --> CAPS
  DDR[DECISION_REGISTER] -- justifies --> CAPS
  MAT[MATURITY_MODEL] -- grades --> CAPS
  AUTH[AUTHORITY_MODEL] -- governs --> DOCS((all docs))
  TRC[TRACEABILITY_STANDARD] -- constrains --> DOCS
  GLO[GLOSSARY] -- defines-terms-for --> DOCS
  CON[CONSTITUTION] -- governs --> SPECS((spec docs))
  VIS[VISION] -- defines --> CON
```

## 4. Lineage edges (the central hazard)

```mermaid
flowchart LR
  HEAD[HEAD 6bec9c4] -- contains --> VUE[video-use, skills, memory-data, timeline_to_edl]
  HEAD -- contains-only-as-pyc --> SHELL[learning spine, WF-1/2, MCP, render_to_memory]
  HIST[h1-foundation lineage] -- has-source-for --> SHELL
  SHELL -. must-be-restored DD-009 .-> HEAD
```

## 5. Edge inventory (summary)

| Edge type | Count (approx) | Notes |
|---|---|---|
| reads/writes (memory) | 6 | only via CAP-014 (DD-002) |
| produces/consumes (pipeline) | 12 | WF-1→WF-2→engine→external |
| governs/defines (docs) | 15 | authority + traceability |
| supports/justifies (EV/DD→CAP) | 60+ | the traceability spine |
| broken/intended | 1 | LOOP⇏REC (EV-025) |

Nodes across all types are reachable; the only intentionally broken edge is the documented
open loop. A JSON serialization will make these edges queryable (Phase 2.9).
