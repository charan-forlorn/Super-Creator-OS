# Evidence Register (`EV-xxx`)

> **Status:** ACTIVE (Phase 2.5). Atomized from `../_evidence/EVIDENCE_LEDGER.md` and
> direct live verification on `HEAD 6bec9c4` (2026-06-27). Each row is one atomic,
> repository-verifiable claim. **Repository is the source of truth**; if an `EV` conflicts
> with the live repo, the repo wins and the `EV` is corrected (never deleted).
>
> **Confidence:** HIGH = directly verified in this checkout today · MED = sourced from a
> read-only audit of an unmerged lineage, not re-verifiable from HEAD · LOW = heuristic.
> **Verified:** `V` = verified live 2026-06-27 · `A` = from audit reports dated 2026-06-22.

| ID | Claim | Repo path / source | Conf | V/A |
|---|---|---|---|---|
| EV-001 | Mission: build an AI Creative Studio (brief→assets→reference→story→edit→subtitle→grade→QA→caption→export) at near-human-editor quality | `source/_Super Creator OS V.1.md` | HIGH | A |
| EV-002 | Core principle: Claude is Creative Director/Storyteller/Editor Supervisor/QA — **not** the renderer; rendering via FFmpeg/Remotion/CapCut/DaVinci | `source/_Super Creator OS V.1.md` | HIGH | A |
| EV-003 | Creative philosophy: Human First · AI Assisted · Emotion Driven · Story Before Effects · Retention Before Beauty | `source/_Super Creator OS V.1.md` | HIGH | A |
| EV-004 | Architecture is offline, additive, event-driven; no paid APIs / network / ML weights in core path | `project_audit/architecture_audit.md` §1 | HIGH | A |
| EV-005 | Two halves (video execution / stdlib learning) joined only through `memory/` | `project_audit/architecture_audit.md` §1 | HIGH | A |
| EV-006 | Orchestration is document-driven: orchestrator is a prompt, not a code service | `skills/orchestrator/SKILL.md` | HIGH | V |
| EV-007 | 11 subsystems enumerated (orchestrator, 6 skills, video pipeline, WF-1, WF-2, adapter, learning, memory, MCP, uigen, data-infra) | `project_audit/architecture_audit.md` §2 | MED | A |
| EV-008 | `validators.py` is the pure contract hub; `numpy` is the hard dep gating the execution layer; learning layer has zero third-party deps | `project_audit/architecture_audit.md` §4 | MED | A |
| EV-009 | 15-step pipeline: Brief→Assets→References→Concept→Story→Timeline→Motion→Color→Subtitle→Retention→QA→Render→Export→Captions→Archive | `workflow-map.md` | HIGH | V |
| EV-010 | Memory protocol: STEP 1 READ `database.json` (nearest `product_niche`), STEP 15 WRITE (append, never overwrite) | `skills/orchestrator/SKILL.md` | HIGH | V |
| EV-011 | WF-1 = highlight + narrative; WF-2 = short + montage; WF-3 = observed telemetry capture | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-012 | Seven skill/role contracts present as prompts | `skills/{orchestrator,storytelling,video-editor,qa-reviewer,retention-expert,social-media-manager}/*.md` | HIGH | V |
| EV-013 | Memory schema v1 required fields: project_name, product_niche, hook_successful, editing_specs, retention_score (0–100), lesson_learned, created_at | `memory/schema.md` | HIGH | V |
| EV-014 | Memory schema v2 additive-optional fields (engine, transcribed, edl_path, grade_used, subtitle_source, cut_padding_ms, render_specs) | `memory/schema_v2_extension.md` | HIGH | V |
| EV-015 | Live `database.json` = 2 records, v1 keys only, UTF-8 (default cp1252 read fails) | `memory/database.json` | HIGH | V |
| EV-016 | `memory/telemetry.json` does not exist (0 observed-outcome rows) | filesystem | HIGH | V |
| EV-017 | `safe_append` write-path = integrity pre-check + schema validation + timestamped backup + append-only post-condition + atomic os.replace + write-token guard + dedup + tamper-evident sha256 marker | `project_audit/memory_audit.md` §2 | MED | A |
| EV-018 | `video-use` engine present & runnable: `vu.py` + 7 helpers; numpy 2.4.3 + mcp importable; Python 3.11.15 | `integrations/video-use/` | HIGH | V |
| EV-019 | MCP surface = 11 FastMCP tools (probe, volume_stats, scene_cuts, extract_frames, extract_audio, trim, mux_audio, grade, burn_subtitles, concat_list, analyze_virality) | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-020 | Highlight detection fuses audio RMS + motion + onset → peaks → candidates (deterministic, no ML) | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-021 | Narrative engine extracts buildup→climax→resolution with a Buildup Sufficiency Gate + arc scoring (heuristic) | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-022 | Generation: `short_generator` single-pass; `montage` beat-sync + 9:16 reframe + ducking + FX | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-023 | Semantic highlight labels require an unsupplied `VisualEventDetector` (default `NullVisualDetector`) | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-024 | Intended learning loop: telemetry→join on loop_run_id→evaluate→calibrated_benchmark→recommend→render→build_record(+provenance)→safe_append | `project_audit/learning_loop_audit.md` §1 | MED | A |
| EV-025 | L1: `calibrated_benchmark()` is consumed by nothing (HIGH) | `project_audit/learning_loop_audit.md` | MED | A |
| EV-026 | L2: CLI render stamps no provenance ⇒ records unjoinable (HIGH) | `project_audit/learning_loop_audit.md` | MED | A |
| EV-027 | L3: zero observed telemetry rows ⇒ loop closure unproven on real data | `project_audit/learning_loop_audit.md` | HIGH | V |
| EV-028 | Hallucinated-learning risk LOW by design: capture rejects predicted-looking keys; residual risk is under-learning | `project_audit/learning_loop_audit.md` §5 | MED | A |
| EV-029 | Threat model = local, offline, single-user (not a network service) | `project_audit/security_audit.md` | HIGH | A |
| EV-030 | Runtime now provisioned: CPython 3.11.15, numpy 2.4.3, mcp importable (audit's #1 blocker resolved at interpreter level) | venv check | HIGH | V |
| EV-031 | No root `requirements.txt` in HEAD | filesystem | HIGH | V |
| EV-032 | Lineage divergence: HEAD `6bec9c4` is a 4-commit chain distinct from the audited 24-commit `h1-foundation` | `git log` | HIGH | V |
| EV-033 | Learning spine, WF-1/WF-2, MCP, `render_to_memory` are **absent as `.py` source** in HEAD — orphaned `.pyc` only | filesystem scan | HIGH | V |
| EV-034 | 0 tracked `.pyc`; the 38 learning `.py` files were added on the other lineage (reachable via `git log --all`, not in HEAD tree) | `git ls-files`, `git log --all` | HIGH | V |
| EV-035 | Founder 7-phase roadmap: Skill System→Project Memory→Video Analysis MCP→FFmpeg Render→Browser/Computer Control→Self-Improving Brain→Autonomous Agent | `source/_Super Creator OS V.1.md` | HIGH | A |
| EV-036 | Audit H2: verify/promote video layer (CI + smoke + real detector), operate closed loop on real telemetry, scale hardening | `project_audit/next_steps.md`, `project_health_report.md` | MED | A |
| EV-037 | Prioritized backlog P0 (merge, provision, close loop, smoke) / P1 (e2e test, dedup, CI, bound growth) / P2 (O(1) append, detector, portability) | `project_audit/next_steps.md` | MED | A |
| EV-038 | ADDITIVE discipline: never edit a core file; extend additively (commit convention) | `project_audit/architecture_audit.md` §1; `memory/schema_v2_extension.md` | HIGH | A |
| EV-039 | Single safe write path enforced (commit `cd26b79` "Boundary A"); CLI routes writes through `safe_append` | `project_audit/memory_audit.md` §2 | MED | A |
| EV-040 | Observed-only telemetry: capture rejects predicted metrics (`PREDICTED_FORBIDDEN`); warns when observed == predicted | `project_audit/learning_loop_audit.md` §5 | MED | A |
| EV-041 | Immutable v1 contract: `validators.V1_REQUIRED` freezes v1; v2/v3 optional/additive | `project_audit/next_steps.md` Q4 | MED | A |
| EV-042 | Analysis is heuristic/deterministic — no model weights | `project_audit/video_intelligence_audit.md` | MED | A |
| EV-043 | O(n²) memory/telemetry append cost (validate-all + full compare + full copy per write) | `project_audit/performance_audit.md` P1 | MED | A |
| EV-044 | Unbounded growth: `_db_backups/`, `_telemetry_backups/`, `events.jsonl`, `work/seeds/` never pruned | `project_audit/memory_audit.md` M3; `performance_audit.md` P3 | MED | A |
| EV-045 | Validation logic duplicated (`render_to_memory` re-implements vs `validators.py`) (M2) | `project_audit/memory_audit.md` | MED | A |
| EV-046 | `eval()` on ffprobe output in MCP (`scos_video_mcp.py:34`) (S1) | `project_audit/security_audit.md` | MED | A |
| EV-047 | Machine-specific absolute paths in `work/uigen/` (S3) | `project_audit/security_audit.md` | MED | A |
| EV-048 | MCP file tools have no path allow-listing (S4 — LOW local / HIGH if remoted) | `project_audit/security_audit.md` | MED | A |
| EV-049 | Tests: learning layer 82/82 green; video/adapter/mcp 0 runnable in audit env; no CI/coverage/e2e | `project_audit/testing_audit.md` | MED | A |
| EV-050 | `render_to_memory` (loop-critical writer) has zero tests (T2) | `project_audit/testing_audit.md` | MED | A |
| EV-051 | Overall project health 68/100 ("Strong foundation, unverified frontier") | `project_audit/project_health_report.md` | MED | A |
| EV-052 | Blueprint templates exist: project_brief, story_arc, timeline_format, captions, retention_report | `source/super_creator_blueprints/*.md` | HIGH | V |
| EV-053 | Root `README.md` is effectively empty (single title line) | `README.md` | HIGH | V |
| EV-054 | `timeline_to_edl.py` is present as `.py` source in HEAD (lineage-A) | `integrations/adapter/timeline_to_edl.py` | HIGH | V |
| EV-055 | `_backup_pre_integration_2026-06-15/` is tracked (17 files incl. duplicate `database.json`) (G3) | `git ls-files` | HIGH | V |

**Total: 55 evidence items.** Confidence: HIGH=27, MED=28. Verification basis: live (V)=19,
audit-sourced (A)=36 — i.e. **65% of evidence is audit-sourced and stale-risk** until
re-verified against HEAD (see `REPOSITORY_INTELLIGENCE.md` §6). _(Counts verified by grep
2026-06-27.)_
