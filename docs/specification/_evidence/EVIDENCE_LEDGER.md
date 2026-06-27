# Evidence Ledger — Super Creator OS Specification Layer

> **Phase 2 deliverable.** This ledger stores the repository evidence that every
> specification document (Phases 3–13) must cite. It is **evidence**, not
> specification: it records what the repository *contains*, with provenance, and
> reconciles it against the prior audit reports.
>
> **Baseline:** current detached `HEAD = 6bec9c4` (`fix: 3 Windows-compat fixes +
> real-footage validation`), per the ratified decision *"current checkout is truth."*
> **Verification date:** 2026-06-27. **Mode:** read-only.

> **Phase 2.7 annotation (additive — no prose changed below).** This narrative ledger is
> the **source**; its claims were atomized into stable IDs in
> [`../_knowledge/EVIDENCE_REGISTER.md`](../_knowledge/EVIDENCE_REGISTER.md) (`EV-001…EV-055`)
> and the decisions into [`../_knowledge/DECISION_REGISTER.md`](../_knowledge/DECISION_REGISTER.md)
> (`DD-001…DD-014`). Cite the `EV`/`DD` IDs in specs, not raw ledger prose. Section map:
> §0→EV-032/033/034 · §1→EV-001/002/003 · §2→EV-004/005/006/007/008 · §3→EV-009/010/011 ·
> §4→EV-012 · §5→EV-013/014/015/016/017 · §6→EV-018/019/054/030 · §7→EV-020/021/022/023 ·
> §8→EV-024/025/026/027/028 · §9→EV-029/030/031 · §10→EV-035/036/037 · §11→EV-052/053 ·
> §12→DD-001/002/003/004/005.

---

## 0. CRITICAL RECONCILIATION — Two lineages in one repository

The 12 `project_audit/*.md` reports (dated 2026-06-22) describe branch
`h1-foundation`. **The current checkout is a different lineage.** Verified:

| Aspect | Audited `h1-foundation` (historical) | Current `HEAD 6bec9c4` (truth) |
|---|---|---|
| Commit chain | `6cf22fc → … → fb54329 → … → 42cafdd` (24 commits) | `51e3835 Initial → 9eed1e0 baseline → f3668fb video-use integration → 6bec9c4` (4 commits) |
| Learning spine `.py` (`integrations/learning/*.py`) | present, tested 82/82 | **absent as source** — only orphaned `.pyc` in `__pycache__/` |
| WF-1/WF-2 engines (`highlight/`, `shortgen/`) | present | **absent as source** — orphaned `.pyc` only |
| MCP server (`integrations/mcp/scos_video_mcp.py`) | present | **absent as source** — orphaned `.pyc` only |
| Adapter `render_to_memory.py` | present | **absent as source** — orphaned `.pyc` only |
| `video-use` engine (`integrations/video-use/`) | not yet integrated | **present as real source** (newly integrated, commit `f3668fb`) |
| Python runtime | 3.15.0b1 (wrong) | **3.11.15 (correct, matches pin)** |
| numpy / mcp installed | no | **yes** (`numpy 2.4.3`, `mcp` importable) |
| `requirements.txt` at root | present (commit `8954866`) | **absent** |

**Evidence commands (2026-06-27):**
- `git rev-parse HEAD` → `6bec9c41…`; `git status -sb` → `## HEAD (no branch)` (detached).
- `git log --oneline -5` → the 4-commit chain above.
- `find integrations work -name "*.py" -not -path "*/__pycache__/*"` → only
  `integrations/adapter/timeline_to_edl.py`, the `video-use` engine (`vu.py` + 7
  helpers), and `work/uigen/build_lyric.py`.
- Orphaned-`.pyc` scan → `render_to_memory`, `highlight_engine`, `narrative_engine`,
  `montage`, `short_generator`, `scos_video_mcp`, and the whole `learning/` set
  exist **only** as `.pyc` (mixed `cpython-311` and `cpython-315`) with no `.py`.
- `git ls-files "*.pyc"` → **0** (the `.pyc` are untracked local artifacts).
- `git log --all --diff-filter=A` shows the 38 learning `.py` files were added on the
  other lineage (`6cf22fc`, `fb54329`, `1d92068`, `cd26b79`) — reachable in history,
  **not** in the current HEAD tree.

**Implication for all specifications:** Where an audit credits a capability to the
learning spine or video-intelligence modules, that capability is **proven on the
`h1-foundation` lineage but NOT runnable from this checkout** until those modules are
restored/merged into HEAD. Each spec must distinguish:
- **(A) Present & runnable now** — `video-use` engine, skills/prompts, memory data.
- **(B) In history, not in HEAD** — learning spine, WF-1/2, MCP, adapter writer.
- **(C) Planned / unbuilt** — anything in the roadmap not yet coded on any lineage.

---

## 1. System purpose

- **Mission (source of truth):** `source/_Super Creator OS V.1.md` — *"สร้าง AI
  Creative Studio"* that analyzes brief/assets/reference, plans story, edits video,
  subtitles, color-grades, QA's, captions, and exports to multiple platforms **at
  near-human-editor quality.**
- **Core principle (ibid.):** *"Claude ไม่ใช่ Video Editor"* — Claude is **Creative
  Director / Storyteller / Editor Supervisor / QA Reviewer**; actual rendering is done
  by **FFmpeg / Remotion / CapCut / DaVinci automation.**
- **Creative philosophy (ibid.):** Human First · AI Assisted · Emotion Driven · Story
  Before Effects · Retention Before Beauty.
- **Architecture characterization:** `project_audit/architecture_audit.md` §1 —
  *"offline, additive, event-driven content pipeline"*; *"every commit message:
  'ADDITIVE / never edits a core file'."*

## 2. Architecture

- **Two halves joined by `memory/`** (`architecture_audit.md` §1): an **execution
  layer** (video: ffmpeg + numpy, no paid APIs/network/ML weights) and a **learning
  layer** (stdlib-only knowledge).
- **Coordination is document-driven**: the Orchestrator is a *skill prompt*
  (`skills/orchestrator/SKILL.md`), not a code service; Python modules are CLI tools +
  importable functions wired by the documented 15-step procedure and an in-process
  `EventBus`. (`architecture_audit.md` §1.)
- **11 subsystems** enumerated in `architecture_audit.md` §2 (Orchestrator, 6 Skills,
  Video pipeline, WF-1, WF-2, Return adapter, Learning layer, Memory, MCP, UI-gen,
  Data infra). *NOTE: subsystems 3–7, 9 are lineage-(B) in this checkout.*
- **Contract hub:** `validators.py` (pure, no deps); `numpy` is the hard dependency
  gating the execution layer; learning layer has zero third-party deps.
  (`architecture_audit.md` §4.) *(Lineage-B here.)*

## 3. Workflows

- **The 15-step pipeline** (`workflow-map.md`, `skills/orchestrator/SKILL.md`):
  Receive Brief → Analyze Assets → Analyze References → Concept → Story Arc →
  Timeline → Motion Plan → Look Direction → Subtitle Plan → Retention Risk → QA
  (Pass/Fail) → Render → Export (TikTok/IG Reel/IG Story) → Captions → Archive.
- **STEP 1 = READ memory, STEP 15 = WRITE memory** (`skills/orchestrator/SKILL.md`
  "Memory Protocol"): read `memory/database.json`, find nearest `product_niche`
  reference, reuse `hook_successful`/`editing_specs`/`lesson_learned`; on Archive,
  append one record (read array → push → write back, never overwrite).
- **WF definitions** (`video_intelligence_audit.md`): WF-1 = auto highlight +
  narrative episode; WF-2 = auto short + music montage; WF-3 = observed telemetry
  capture.

## 4. Agents / Skills

Seven prompt contracts under `skills/` (all lineage-A, present):
`orchestrator/SKILL.md`, `storytelling/SKILL.md`, `video-editor/{SKILL,ENGINE}.md`,
`qa-reviewer/SKILL.md`, `retention-expert/SKILL.md`, `social-media-manager/SKILL.md`.
Roles & outputs defined in `source/_Super Creator OS V.1.md` (storytelling → story
arc/beats/hooks; video-editor → EDL/timeline/shot list; retention-expert → 0–10
scores + drop-off risk; qa-reviewer → PASS/FAIL checklist).

## 5. Memory

- **Schema v1 (required):** `memory/schema.md` — `project_name, product_niche,
  hook_successful, editing_specs, retention_score (0–100), lesson_learned,
  created_at`. JSON array, append-only, empty = `[]`.
- **Schema v2 (additive optional):** `memory/schema_v2_extension.md` — `engine,
  transcribed, edl_path, grade_used, subtitle_source, cut_padding_ms, render_specs{…}`.
  Backward-compatible by construction; old records stay valid.
- **Live state (verified):** `memory/database.json` = **2 records** (v1 keys only,
  no provenance), UTF-8 (must read with `encoding="utf-8"`; default cp1252 fails).
  `memory/telemetry.json` = **does not exist** (0 observed rows).
  *(Audit reported 4 records on h1-foundation; this checkout has 2.)*
- **Write-path guarantees** (`memory_audit.md` §2, lineage-B): `safe_append` =
  integrity pre-check + schema validation + timestamped backup + append-only
  post-condition + atomic `os.replace` + write-token guard + dedup + tamper-evident
  sha256 marker. Scored **88–90/100, production-ready** *on h1-foundation* —
  **not present as source in HEAD.**

## 6. Integrations

- **`video-use` engine (lineage-A, present):** `integrations/video-use/vu.py` +
  `engine/helpers/{render,grade,timeline_view,transcribe,pack_transcripts,
  transcribe_batch}.py`. Deps declared in `engine/pyproject.toml` (requests, librosa,
  matplotlib, pillow, numpy; optional manim; `requires-python >=3.10`).
- **MCP surface (lineage-B):** `scos_video_mcp.py` — 11 FastMCP tools (probe,
  volume_stats, scene_cuts, extract_frames, extract_audio, trim, mux_audio, grade,
  burn_subtitles, concat_list, analyze_virality). (`video_intelligence_audit.md`.)
- **Adapter (mixed):** `timeline_to_edl.py` present (lineage-A);
  `render_to_memory.py` lineage-B (orphaned `.pyc` only).
- **Runtime now provisioned:** Python **3.11.15**, `numpy 2.4.3`, `mcp` importable
  (verified) — the audit's #1 blocker (un-runnable env) is **resolved at the
  interpreter level**, though the source it would run is largely lineage-B.

## 7. AI pipeline (analysis & generation)

- **Highlight detection** (`highlight_engine.detect_highlights`): fuses audio RMS +
  motion + onset → peaks → candidates. **Deterministic, no ML weights.**
- **Story extraction** (`narrative_engine.detect_episodes`): buildup→climax→
  resolution with a Buildup Sufficiency Gate and arc scoring (heuristic, not LLM).
- **Generation** (`short_generator.render_short` single-pass; `montage.render_montage`
  / `render_highlight_60s` beat-sync + 9:16 reframe + ducking + FX).
- **Semantic labels** require an unsupplied `VisualEventDetector` (default
  `NullVisualDetector`). All of §7 is **lineage-B** (source not in HEAD).
  (`video_intelligence_audit.md`.)

## 8. Learning loop

- **Intended loop** (`learning_loop_audit.md` §1): observed telemetry → join on
  `loop_run_id` → `learning_evaluator.evaluate` (mae/bias/observed_benchmark) →
  `calibrated_benchmark` → `recommendation_service.recommend` → render →
  `render_to_memory.build_record(+provenance)` → `safe_append`.
- **Status: well-engineered OPEN loop** (ibid. §6). Three breaks: **L1** —
  `calibrated_benchmark()` consumed by nothing; **L2** — CLI render stamps no
  provenance ⇒ records unjoinable; **L3** — 0 observed telemetry rows. All HIGH.
- **Hallucinated-learning risk: LOW by design** — telemetry rejects predicted-looking
  keys; the residual risk is *under-learning*, not invented learning.
- *Entire loop is lineage-B; `calibrated_benchmark` appears in HEAD only as `.pyc`.*

## 9. Deployment / runtime

- **Local-first, offline, single-user** threat model (`security_audit.md` header).
  No network, no paid APIs in the core video path (`architecture_audit.md` §1).
- **Runtime contract:** CPython 3.11 (pinned; now satisfied), ffmpeg/ffprobe on PATH
  (declared), numpy for the execution layer. No CI configured (`testing_audit.md`).
- **No root `requirements.txt` in HEAD** (verified) — dependency manifest currently
  lives only in `integrations/video-use/engine/pyproject.toml` and in lineage-A
  history (commit `8954866`).

## 10. Roadmap evidence

- **Founder roadmap** (`source/_Super Creator OS V.1.md`, 7 phases): Skill System →
  Project Memory → Video Analysis MCP → FFmpeg Render Engine → Browser/Computer
  Control → Self-Improving Creator Brain → Fully Autonomous Creator Agent.
  Stated priority: build Skill Library + Creator Memory + Reference Database FIRST;
  Browser/Computer Use come last.
- **Audit "H2" recommendation** (`next_steps.md`, `project_health_report.md`): verify
  & promote video layer (CI + smoke renders + real VisualEventDetector); operate the
  closed loop on real telemetry; scale hardening (O(1) appends, retention pruning).
- **Prioritized backlog:** `next_steps.md` P0 (merge, provision runtime, close loop,
  smoke test), P1 (e2e test, dedup validation, CI, bound growth), P2 (O(1) append,
  detector, portability, calibration cache, MCP allow-listing).

## 11. Documentation inventory

- Vision: `source/_Super Creator OS V.1.md`; blueprints in
  `source/super_creator_blueprints/{project_brief,story_arc,timeline_format,
  captions,retention_report}.md`.
- Workflow: `workflow-map.md`. Skills: `skills/*/SKILL.md`. Data: `memory/schema*.md`.
- Audits: 12 reports in `project_audit/` (read-only, dated 2026-06-22, branch
  `h1-foundation`).
- `README.md` (root) = single line `# Super-Creator-OS` (effectively empty).

## 12. Design decisions (recorded)

- **ADDITIVE discipline:** never edit a core file; extend additively (commit-message
  convention, `architecture_audit.md` §1; `schema_v2_extension.md`).
- **Single safe write path:** all memory writes route through `safe_append`
  (`memory_audit.md` §2); commit `cd26b79` "enforce single safe write path (Boundary A)".
- **Observed-only telemetry:** predicted metrics are rejected at capture
  (`learning_loop_audit.md` §5) — the system refuses to fabricate learning.
- **Immutable v1 contract:** `validators.V1_REQUIRED` freezes v1; v2/v3 are optional
  (`next_steps.md` Q4: "what should never be changed").
- **Heuristic, not ML:** highlight/narrative use deterministic signal fusion, no model
  weights (`video_intelligence_audit.md`).

---

## Confidence & caveats

- **HIGH** confidence on lineage reconciliation, live file presence, runtime versions,
  memory record count, telemetry absence (all directly verified 2026-06-27).
- **MEDIUM–HIGH** confidence on lineage-B capability descriptions: sourced from the
  audit reports (which executed/read the code on `h1-foundation`) but **not
  re-verifiable from this checkout** because the source is absent here.
- The audits remain the best evidence for *what the full system does*; this ledger
  governs *what is true in the current checkout*. Specifications must label every
  capability **A / B / C** per §0.
