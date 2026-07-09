# Super-Creator-OS

An **autonomous, AI-driven video creation and learning system** that transforms raw footage into production-grade content through intelligent storytelling, retention analytics, and persistent memory.

**Tech Stack:** Python 86.5% | TypeScript 13.3% | Other 0.2%  
**Status:** Active development (Last Updated: July 9, 2026)

---

## 🎯 Current Status & Recent Milestones

### Latest Progress (July 3-6, 2026)
- ✅ **Control Center Stage 5.2**: AI Work Session Manager (deterministic local
  task/runtime/status modeling for ChatGPT, Claude Code, Codex, Hermes — no AI
  execution, no automation)
- ✅ **Control Center Stage 5.1**: Local command bridge (draft → validate →
  operator approval → JSONL queue → allowlisted runner → event log)
- ✅ **Commercial Stage 4.19**: Final commercial release gate
- ✅ **Commercial Stage 4.17**: First customer conversion handoff
- ✅ **Commercial Stage 4.16**: First prospect outcome review  
- 🎨 **UI Enhancements**: 
  - AI Work Sessions, Agent Routing, and Agent Result Status panels (Stage 5.2 mock)
  - Evidence command center added
  - Operator review & commit gate flow
  - Deterministic live work updates
  - Control center operator workflow clarified
- 🔧 **Infrastructure**: Next.js/Vercel deployment compatibility updated

---

## 🎬 What This Does

Super-Creator-OS is a **brain + hands** video production architecture:

- **Brain** (Super Creator OS core)
  - Story strategy & narrative arc detection
  - Retention hook discovery & placement
  - Editing blueprint generation
  - QA review & learning feedback loops
  - Persistent memory that improves over time

- **Hands** (video-use integration)
  - Frame-accurate video rendering (ffmpeg-based)
  - Word-level speech transcription (ElevenLabs Scribe API)
  - Automated color grading & clip analysis
  - EDL timeline compilation

The system completes a **closed learning loop**: rendered output → observed engagement metrics → calibrated recommendations → smarter next project.

---

## 🏗️ Architecture

```
super-creator-os/
├── skills/                          # Active skill agents (5 concurrent roles)
│   ├── orchestrator/                # Workflow controller
│   ├── storytelling/                # Arc & hook detection
│   ├── video-editor/                # Timeline blueprint generation
│   ├── qa-reviewer/                 # Output validation
│   ├── retention-expert/            # Engagement prediction
│   ├── social-media-manager/        # Platform-specific optimization
│   └── SKILL.md                     # Skill contract template
│
├── discovered_skills/               # Experimental/legacy skills (read-only to orchestrator)
│   └── (migrated after review)
│
├── integrations/                    # Bridge to external engines
│   ├── video-use/                   # Vendored video rendering engine (MIT licensed)
│   │   ├── vu.py                    # Windows-safe launcher (UTF-8 forced)
│   │   ├── engine/                  # Unmodified video-use (2 Windows compat patches)
│   │   │   ├── helpers/             # Transcribe, render, grade, timeline_view
│   │   │   ├── manim-video/         # Optional animation sub-skill
│   │   │   └── LICENSE              # MIT (Browser Use)
│   │   └── .env                     # ELEVENLABS_API_KEY storage
│   │
│   ├── adapter/
│   │   ├── timeline_to_edl.py       # Forward bridge: SCOS timeline → video-use EDL + SRT
│   │   └── render_to_memory.py      # Return bridge: render results → memory/database.json
│   │
│   ├── learning/                    # Closed-loop learning layer
│   │   ├── learning_manager.py      # Orchestrates QA → memory handoff
│   │   ├── learning_evaluator.py    # Per-niche calibration & prediction error tracking
│   │   ├── telemetry_capture.py     # Observed metrics ingestion (manual + API adapters)
│   │   ├── archive_manager.py       # Provenance snapshots
│   │   ├── anchor_library.py        # Narrative highlights per niche
│   │   ├── database.json            # Append-only memory (backed up to _db_backups/)
│   │   ├── validators/              # Data quality contracts
│   │   └── telemetry.py             # Safe, read-only storage layer
│   │
│   └── highlight/                   # Narrative detection
│       ├── narrative_engine.py      # HOOK→BUILD→PEAK→RESOLUTION arc detection
│       └── highlight_engine/        # Signal processing (audio/motion/fuse)
│
├── memory/
│   ├── database.json                # Canonical append-only record of every completed project
│   ├── _db_backups/                 # Automated pre-write backups
│   └── reference.md                 # Human-readable metadata index
│
├── input/
│   └── reference/                   # Source video folder (auto-deleted post-job per WF-1)
│
├── output/
│   └── (renders, SRT, EDL, QA reports)
│
├── work/                            # Temp workspace (EDL, transcripts, grading)
│   └── edit/
│       ├── edl.json                 # Render specification
│       ├── transcripts/             # Word-level Scribe JSON
│       └── qa.json                  # QA pass/fail + notes
│
└── README.md & workflow-map.md      # This file + execution guides

```

---

## 🔄 The Workflow (12 Steps)

Super-Creator-OS executes a deterministic pipeline:

1. **Ingest** — Load source video(s) into `input/reference/`
2. **Transcribe** — ElevenLabs Scribe API (word-level, diarized) → `work/edit/transcripts/`
3. **Story Discovery** — Narrative engine detects HOOK→BUILD→PEAK arcs
4. **Blueprint** — Video Editor generates timeline_format.md with cut timings & captions
5. **Editing Specs** — Serialized cut strategy (clip_type, retention_intent, grade)
6. **EDL Generation** — Adapter converts timeline → video-use EDL + burn-ready SRT
7. **Render** — video-use renders final MP4 with embedded captions
8. **Color Grade** — Auto-analysis or preset application (no creative shift by default)
9. **QA Review** — Reviewer validates cuts, captions, retention integrity
    - **FAIL** → log, do NOT write to memory, re-edit
    - **PASS** → proceed to learning
10. **Memory Record** — Append structured project record to `memory/database.json` (atomic, backed up)
11. **Archival** — Store project metadata & provenance in `integrations/learning/archive/<project>/`
12. **Calibration** — Update per-niche retention benchmarks & highlight library

On **QA PASS**: source files in `input/reference/` are auto-deleted (per WF-1 standing order).

---

## 🧠 The Learning Loop (Closed-Loop AI)

After each project completes:

### Observed Metrics Flow
1. **Collect** — Real engagement data (views, watch%, completion_rate, rewatch_rate, etc.) via manual entry or API adapter
2. **Store** — `telemetry_capture.py` validates and ingests into `memory/database.json` (separate telemetry index)
3. **Evaluate** — `learning_evaluator.py` compares predicted vs. observed retention
4. **Calibrate** — Per-niche MAE, bias, benchmark updates
5. **Seed** — Next project recommendations seeded with observed benchmarks instead of predictions

### Knowledge Artifacts
- **highlight_anchor_library** — Narrative patterns (HOOK placement, BUILD duration, PEAK prominence) that drove high retention
- **editing_specs_log** — Which cut strategies, caption styles, color grades correlated with engagement
- **retention_score_calibration** — Prediction error tracking per content niche/platform

**Contract:** Every training record includes:
- Predicted retention (from original decision)
- Observed watch% (from telemetry)
- Prediction error
- Hooks used
- Editing specs applied
- Render success boolean

---

## 🚀 Quick Start

### Prerequisites
```bash
python 3.9+
ffmpeg, ffprobe (system PATH)
ElevenLabs API key (for transcription)
```

### Setup
```bash
# Clone & enter
git clone https://github.com/charan-forlorn/Super-Creator-OS.git
cd Super-Creator-OS

# Install Python deps
uv pip install -r requirements.txt  # or pip install

# Copy .env template
cp integrations/video-use/.env.example integrations/video-use/.env
# Edit with your ELEVENLABS_API_KEY
```

### Render a Timeline (End-to-End)

```bash
# 1. Convert SCOS timeline → EDL + SRT
python integrations/adapter/timeline_to_edl.py \
    source/blueprints/timeline_format.md \
    --assets-dir input/frames \
    -o work/edit/edl.json \
    --grade warm_cinematic

# 2. Render (--preview for 720p draft)
python integrations/video-use/vu.py render work/edit/edl.json \
    -o work/edit/final.mp4

# 3. QA check (visual inspection)
python integrations/video-use/vu.py timeline_view work/edit/final.mp4 120 180

# 4. If QA passes, write learning record
python integrations/learning/learning_manager.py \
    --edl work/edit/edl.json \
    --render work/edit/final.mp4 \
    --transcripts-dir work/edit/transcripts \
    --project-name "My Project" \
    --product-niche "gaming" \
    --qa-pass true \
    --retention-score 82

# 5. Done! Source cleaned automatically after memory write.
```

### Key Commands

| Task | Command |
|------|---------|
| Batch transcribe videos | `python integrations/video-use/vu.py transcribe_batch <videos_dir> --workers 4` |
| Auto color grade analysis | `python integrations/video-use/vu.py grade --analyze <clip.mp4>` |
| Pack transcripts for editor | `python integrations/video-use/vu.py pack_transcripts --edit-dir work/edit` |
| Dry-run learning record (preview before write) | `python integrations/learning/learning_manager.py ... --dry-run` |
| Evaluate model calibration | `python -c "from integrations.learning.learning_evaluator import evaluate; print(evaluate())"` |

---

## 🔐 Data Integrity & Safeguards

### Memory Safety
- **Append-only** — database.json never overwrites; all writes are new records
- **Atomic** — Pre-write backup to `memory/_db_backups/` before any append
- **Validator layer** — `telemetry_capture.py` catches:
  - Predicted metric leaks (predicted_retention in observed data → REJECTED)
  - Invalid date ranges
  - Negative metrics where not allowed
  - Missing required fields (loop_run_id, platform, collected_at)

### Rendering Safety
- **Windows compat** — `vu.py` launcher forces UTF-8 encoding (prevents console crashes on Windows)
- **EDL validation** — adapter rejects timeline entries missing required fields
- **QA gate** — failed renders/QA never write to memory

### Source File Cleanup
Deletions occur **only after all 3 conditions confirmed**:
1. ✅ Output exists in `output/`
2. ✅ Learning record appended to `memory/database.json`
3. ✅ Provenance snapshot exists in `integrations/learning/archive/<project>/`

If **any** condition fails, source is kept (reprocessing safe).

---

## 🧩 Integration & Extensibility

### Custom Adapters
The system is modular. To plug in a new data source:

1. **Telemetry API** — Implement `ApiAdapter` protocol in `integrations/learning/telemetry_capture.py`:
    ```python
    class MyPlatformAdapter:
        def fetch(self, loop_run_id: str, platform: str) -> dict | None:
            # Return observed metrics dict or None
    ```

2. **New Skill** — Add to `skills/` folder, follow `SKILL.md` contract, wire into Orchestrator

3. **Highlight Algorithm** — Extend `integrations/highlight/narrative_engine.py` with new arc detection

### Video-Use Engine
The vendored `integrations/video-use/engine/` is **byte-for-byte upstream** from [browser-use/video-use](https://github.com/browser-use/video-use) (MIT license).

**Only 2 Windows compatibility patches applied** (marked in code):
- `engine/helpers/grade.py` — Relative temp filename for ffmpeg filtergraph compatibility
- `engine/helpers/render.py` — Backslash-to-forward-slash path conversion for SRT filter

Everything else is unmodified. Engine updates can be merged cleanly.

---

## 📊 Memory Schema

### Project Record (database.json entry)
```json
{
  "project_name": "ep_01_gaming_highlights",
  "product_niche": "gaming",
  "created_at": "2026-07-03T12:30:00Z",
  "loop_run_id": "uuid-xxx",
  "predicted_retention_score": 78,
  "editing_specs": {
    "clip_type": ["gameplay", "reaction", "graphic"],
    "subtitle_style": "energetic_sans",
    "cut_padding_ms": [50, 200],
    "grade_used": "warm_cinematic"
  },
  "render_success": true,
  "qa_pass": true,
  "retention_signals": { "hook_placement": "early", "buildup_duration_s": 4.2, ... },
  "observed": [
    {
      "platform": "youtube",
      "collected_at": "2026-07-10T00:00:00Z",
      "avg_watch_pct": 76,
      "completion_rate": 0.71,
      "rewatch_rate_pct": 12
    }
  ]
}
```

---

## 🎯 Roadmap & Next Steps

- [x] **Core architecture** — Brain + hands pipeline complete
- [x] **Commercial stages** — 4.14–4.17 handoff & conversion tracking
- [ ] **Live metrics webhook** — Real-time engagement push (vs. manual collection)
- [ ] **Multi-niche hierarchy** — Sub-niches + cross-niche learning transfer
- [ ] **A/B render variants** — Auto-test 2–3 different edits per project
- [ ] **Soundtrack integration** — Auto-select music based on narrative arc
- [ ] **Subtitle animation** — Kinetic text matching energy peaks

---

## 📝 License

- **Super Creator OS** (core, skills, adapters, learning) — Your code, your license.
- **video-use engine** (`integrations/video-use/engine/`) — MIT © 2026 Browser Use.
- All other vendored dependencies — See individual license files.

---

## 🤝 Contributing

For issues, feature requests, or PRs: [GitHub Issues](https://github.com/charan-forlorn/Super-Creator-OS/issues)

**Before merging learned data or new skills:**
1. Run QA gate (no failed renders)
2. Verify memory record passes validator
3. Archive provenance
4. Document any new Skill contract changes

---

**Made with ❤️ by Charan | Last Updated: July 9, 2026**
