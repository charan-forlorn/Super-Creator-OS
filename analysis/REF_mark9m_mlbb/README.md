# Reverse-Engineering Dossier — `Download.mp4`

**Subject:** Mobile Legends: Bang Bang multi-match kill compilation
**Creator:** TikTok `@mark9m_` (Thai UI, hero "Mark", main skill *Iron Body*)
**Source:** Downloaded from TikTok (AIGC-labeled, ByteDance re-encode)
**Analyzed:** 2026-06-21 · Claude Code (Senior Video RE Team mode)

> Objective of this dossier: **reconstruct the creator's production system** and
> convert it into an automation-ready framework for Super Creator OS (SCOS).

## Evidence base (all conclusions trace here)
- `ffprobe` full stream/format dump
- `scene` detection sweep (thresholds 0.1 / 0.3 / 0.4)
- 60+ extracted frames (2s contact sheets + key frames)
- Fine-grained frames around kill @50.5s (zoom curve)
- **Top-right HUD crops at every scene-peak → read in-game timer + score** (the decisive test that exposed multi-match stitching)
- Audio RMS envelope (1s windows) + silence detection

## File index
| # | File | Phase |
|---|------|-------|
| 01 | `01_executive_summary.md` | Final |
| 02 | `02_forensics_report.md` | Phase 1 |
| 03 | `03_timeline_map.md` | Phase 2 |
| 04 | `04_editing_dna.md` | Phase 3 |
| 05 | `05_retention_heatmap.md` | Phase 4 |
| 06 | `06_psychology_report.md` | Phase 5 |
| 07 | `07_creator_brain.md` | Phase 6 |
| 08 | `08_algorithm_report.md` | Phase 7 |
| 09 | `09_style_bible.md` | Phase 8 |
| 10 | `10_creator_rules.yaml` | Phase 9 (110 rules) |
| 11 | `automation/*.yaml` | Phase 10 |
| 12 | `12_gap_analysis.md` | Phase 11 |
| 13 | `13_replication_accuracy.md` | Final |
| 14 | `14_recommendations_scos.md` | Final |

## THE single most important finding
The video looks like one continuous match. **It is not.** Reading the in-game
timer/score at each transition proves it is **6–9 clips from different matches**,
stitched with **invisible cuts** that hide inside identical map+HUD continuity and
heavy in-game VFX. The creator's real craft is **clip selection + masked cutting +
energy pacing**, not "effects". Everything downstream follows from this.
