# 05 · Retention Heatmap (Phase 4)

## Attention timeline (▇ = energy, ↯ = masked cut / new clip, ★ = climax)
```
0:00  ▅▆▇  cold open + beat drop @0.7  (HOOK)
0:08  ▇▇█ ↯  teamfight, ult ring, item toasts
0:16  ███ ↯  sustained fight (Match C)        ← curiosity: score 10v12, comeback?
0:27  ██▇ ↯
0:43  ███ ↯  build: "Ultimate" + 170g
0:50  ████★   "KILL" + "IMMUNE"  (CLIMAX, on-beat punch-in)
0:52  ███ ↯  cut hidden in kill-flash → Match E
1:10  ███ ↯  Match F, score 27v21
0:90  ███ ↯  dense fight, Ring of Vitality
1:01  ██▇ ↯
1:41  ██▇ ↯  Match G (final clips)
1:55  ▇░░    HARD STOP → black + silence (PATTERN INTERRUPT)
1:56  ░░░    end card @mark9m_  (CTA / FOLLOW)
```

## Retention mechanic inventory
| Mechanic | Where | How it works |
|---|---|---|
| **Open loop (macro)** | whole video | Rising kill score = "how high?" never resolved until end |
| **Open loop (micro)** | each clip | Ult cast / "Ultimate" banner promises an imminent kill |
| **Curiosity trigger** | losing-score clips (10v12, 6v10) | "Will they comeback?" |
| **Pattern interrupt** | every masked cut (~9 s) + final black | Fresh scene resets adaptation |
| **Micro reward** | every "Kill"/banner/damage burst | Dopamine pellet |
| **Escalation** | match selection order | Bigger fights / denser VFX as it runs |
| **Payoff** | 0:50.5 climax kill | The promised resolution |
| **Attention reset** | punch-in zoom per clip | Re-spikes focus without a visible cut |

## Calculated intervals (from verified events)
- **Average reward interval:** ~8–11 s (one highlight payoff per stitched clip).
  - 119 s body ÷ ~7 clips ≈ **9.0 s / reward**.
- **Average curiosity interval:** ~15–20 s (each new match re-poses stakes; ~6 stake-resets).
- **Average attention-spike interval:** ~8–11 s (punch-in + new clip coincide) ≈ **9 s**.
- **Hook latency:** first reward < **8 s**; beat-synced spike at **0.7 s**.
- **Dead-air placement:** only at end (115.7 s), never mid-body → no premature exit cue.

## Heatmap reading
The design is a **flat-high comb**: a reward/spike roughly every 9 seconds, with NO valley
deep enough to trigger a scroll, and the only silence deliberately saved for the CTA. The
"comb spacing" (~9 s) is the load-bearing number — it matches an 8-bar musical phrase at
~80–85 BPM, so audio and visual spikes reinforce.

**Automation target:** keep max gap-between-rewards ≤ 11 s; if a candidate clip has no
payoff within 11 s, trim or drop it.
