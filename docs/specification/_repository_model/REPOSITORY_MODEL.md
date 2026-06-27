# Repository Model

> **Status:** ACTIVE (Phase 2.9.1). Part of the **Repository Intelligence Layer**. A formal
> model of the repository's physical + logical structure so AI agents can locate any module
> without scanning. **Baseline:** `HEAD 6bec9c4`, 2026-06-27. Cites `EV`/`DD`/`CAP` per
> `../_knowledge/TRACEABILITY_STANDARD.md`. Governance: `../_knowledge/AUTHORITY_MODEL.md`
> layer 6 (Implementation). **Non-destructive: describes the lineage hazard, does not fix it.**

---

## 1. Structural hierarchy

```
Repository (super-creator-os, HEAD 6bec9c4)
├── Domains (7)
│   ├── Direction        → skills/
│   ├── Execution/Video  → integrations/{video-use,highlight,shortgen,mcp}
│   ├── Learning         → integrations/{learning,adapter}
│   ├── Memory           → memory/
│   ├── Infrastructure   → .venv/, .vscode/, (requirements.txt: absent EV-031)
│   ├── Documentation    → docs/, source/, project_audit/, workflow-map.md
│   └── Data             → input/, output/, work/
└── Lineages (2)         → HEAD (delivered) vs h1-foundation (unmerged)  [EV-032]
```

## 2. Lineage presence map (the central hazard — EV-032/033/034, DD-009)

| Module group | In HEAD as `.py`? | Note |
|---|---|---|
| `integrations/video-use/**` | ✅ source | runnable; numpy 2.4.3/mcp/py3.11 (EV-018, EV-030) |
| `integrations/adapter/timeline_to_edl.py` | ✅ source | EV-054 |
| `integrations/learning/**` | ❌ `.pyc` only | reference impl on h1-foundation (EV-033) |
| `integrations/highlight/**` | ❌ `.pyc` only | EV-033 |
| `integrations/shortgen/**` | ❌ `.pyc` only | EV-033 |
| `integrations/mcp/scos_video_mcp.py` | ❌ `.pyc` only | EV-033 |
| `integrations/adapter/render_to_memory.py` | ❌ `.pyc` only | EV-033, EV-050 |
| `skills/**`, `memory/*.json|*.md`, `source/**` | ✅ present | EV-012/013/052 |

**Rule for agents:** a `.pyc` without a sibling `.py` is evidence of a **missing** module,
not a present one (`../_knowledge/REPOSITORY_INTELLIGENCE.md` §6).

## 3. Module registry

Per module: purpose · owner · dependencies · consumers · primary docs · capabilities ·
evidence · path. Owners use the `CAPABILITY_REGISTRY.md` role set (Engine/Learning/Skills/
Platform/Memory).

### Direction domain
| Module | Purpose | Owner | Deps | Consumers | Caps | Evidence | Path |
|---|---|---|---|---|---|---|---|
| Orchestrator | Coordinate 15-step pipeline (prompt) | Platform | memory, all skills | operator | CAP-023 | EV-006, EV-009, DD-007 | `skills/orchestrator/SKILL.md` |
| Role skills (5) | storytelling, video-editor, qa-reviewer, retention-expert, social-media-manager | Skills | orchestrator | pipeline | CAP-005/006/011/012/013 | EV-012, EV-003 | `skills/*/SKILL.md` |

### Execution / Video domain
| Module | Purpose | Owner | Deps | Consumers | Caps | Evidence | Path |
|---|---|---|---|---|---|---|---|
| video-use engine | render/grade/transcribe helper engine | Engine | numpy, ffmpeg | MCP, grading, captions | CAP-009/010/020 | EV-018, DD-006 | `integrations/video-use/vu.py` + `engine/helpers/*` |
| highlight (WF-1) | RMS+motion+onset → candidates | Engine | numpy | narrative, shortgen | CAP-003 | EV-020, DD-005, EV-033 | `integrations/highlight/` *(pyc-only)* |
| shortgen (WF-2) | short + montage | Engine | numpy, ffmpeg | export, memory | CAP-007/008 | EV-022, EV-033 | `integrations/shortgen/` *(pyc-only)* |
| MCP server | 11 ffmpeg FastMCP tools | Engine | mcp, ffmpeg | external clients | CAP-019 | EV-019, EV-046, EV-033 | `integrations/mcp/scos_video_mcp.py` *(pyc-only)* |

### Learning domain
| Module | Purpose | Owner | Deps | Consumers | Caps | Evidence | Path |
|---|---|---|---|---|---|---|---|
| memory_writer | single safe write path | Memory | validators | adapter, telemetry | CAP-014 | EV-017, DD-002, EV-033 | `integrations/learning/memory_writer.py` *(pyc-only)* |
| validators | pure contract hub | Memory | — | writer, telemetry | CAP-014 | EV-008, EV-041 | `integrations/learning/validators.py` *(pyc-only)* |
| recommendation_service | creative seed from nearest niche | Learning | memory, anchors | orchestrator | CAP-015 | EV-024, EV-025 | `…/recommendation_service.py` *(pyc-only)* |
| telemetry / telemetry_capture | observed metrics store | Learning | validators | evaluator | CAP-016 | EV-040, DD-003 | `…/telemetry*.py` *(pyc-only)* |
| learning_evaluator | mae/bias/calibrated_benchmark | Learning | telemetry | (loop — broken) | CAP-017/018 | EV-024, EV-025 | `…/learning_evaluator.py` *(pyc-only)* |
| event_bus / dq_report | audit spine / data quality | Platform/Learning | — | dq / maintainer | CAP-021/022 | EV-007, EV-049 | `…/event_bus.py`, `…/dq_report.py` *(pyc-only)* |
| render_to_memory | build+write record (adapter) | Learning | memory_writer | memory | CAP-014/015 | EV-050, EV-045, EV-033 | `integrations/adapter/render_to_memory.py` *(pyc-only)* |
| timeline_to_edl | timeline → EDL | Skills | — | render | CAP-006 | EV-054 | `integrations/adapter/timeline_to_edl.py` ✅ |

### Memory domain
| Module | Purpose | Owner | Deps | Consumers | Caps | Evidence | Path |
|---|---|---|---|---|---|---|---|
| `memory/database.json` | system-of-record (2 records) | Memory | schema | recommend, evaluator | CAP-014 | EV-013, EV-015 | `memory/database.json` ✅ |
| `memory/schema*.md` (v1/v2) | data contract | Memory | — | writer, orchestrator | CAP-014 | EV-013, EV-014 | `memory/schema.md`, `memory/schema_v2_extension.md` ✅ |
| `memory/telemetry.json` | observed outcomes (absent) | Memory | schema | evaluator | CAP-016 | EV-016 | `memory/telemetry.json` *(absent in HEAD)* |

### Infrastructure / Documentation / Data domains
| Module | Purpose | Owner | Evidence | Path |
|---|---|---|---|---|
| runtime | CPython 3.11.15 + numpy 2.4.3 + mcp | Platform | EV-030 | `.venv/` |
| dependency manifest | **missing at root** | Platform | EV-031 | *(absent; only `video-use/engine/pyproject.toml`)* |
| Specification + EKB | this knowledge system | Platform | — | `docs/specification/**` |
| Vision + blueprints | strategy + templates | Platform | EV-001, EV-052 | `source/**` |
| Audits | read-only evidence | Platform | EV-051 | `project_audit/*.md` |
| Working data | raw/intermediate/output media | Engine | — | `input/`, `work/`, `output/` |
| Tracked backup (debt) | duplicate `memory/database.json` | Memory | EV-055 | `_backup_pre_integration_2026-06-15/` |

## 4. Statistics

- **Domains:** 7 · **Lineages:** 2 · **Modules catalogued:** 24.
- **Runnable `.py` in HEAD:** video-use engine (8 files) + `integrations/adapter/timeline_to_edl.py` = **2 module
  groups**; **`.pyc`-only (lineage-B):** 6 module groups (learning, highlight, shortgen, mcp,
  render_to_memory) (EV-033).
- **Capabilities mapped to modules:** 23/23 (CAP-001…023).
- **Owners:** Engine, Learning, Skills, Platform, Memory (no module has two owners).

## 5. How agents use this model

1. Resolve a capability → owner + module + path via this registry.
2. **Check the lineage presence map (§2) before claiming a module runs.**
3. Cite the module's `EV` IDs; verify the path in HEAD per
   `../_knowledge/REPOSITORY_INTELLIGENCE.md`.
