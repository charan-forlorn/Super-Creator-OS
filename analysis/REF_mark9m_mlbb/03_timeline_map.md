# 03 · Timeline Map (Phase 2)

## Method note
The video has **no cuts above scene-score 0.4**, so a naive pass reads it as one shot.
By extracting the **top-right HUD (in-game timer + kill score) at every scene-score
peak**, the illusion breaks: timer and score are *discontinuous* across peaks → the
peaks are **masked clip boundaries between different matches**. Evidence rows are
marked ⟂ (verified by timer/score read).

### Verified match-state reads (the proof)
| Time | In-game timer | Score (blue vs red) | Match |
|---|---|---|---|
| 0:00 | 02:16 | 5 v 0 | A |
| 0:08 | 02:25 | 5 v 0 | A (continuous) |
| 0:15.5 ⟂ | 08:17 | 22 v 12 | B |
| 0:16.5 ⟂ | 10:22 | 10 v 12 | C |
| 0:43.5 ⟂ | 14:47 | 21 v 11 | D |
| 0:48 | 14:52 | 22 v 12 | D (continuous) |
| 0:50 | 14:54 | 23 v 12 | D (+1 kill) |
| 0:53 ⟂ | 13:18 | 22 v 28 | E |
| 1:10.5 ⟂ | 17:21 | 27 v 21 | F |
| 1:41.5 ⟂ | 08:39 | 6 v 10 | G |

→ **At least 6–9 distinct match clips.** Each clip ≈ **8–11 s**.

## Macro structure
| Block | Time | Role |
|---|---|---|
| Cold Open | 0:00–0:08 | Hook — straight into setup→fight, no title |
| Hype Body | 0:08–1:55.7 | Stitched kill clips, energy held high & flat |
| End Card | 1:55.7–1:58.7 | Black + TikTok + `@mark9m_` search bar, **silent** |

## Shot-by-shot map
Legend — VP=Viewer Purpose, CP=Creator Purpose.

| Time | Event | Action | VP (viewer) | CP (creator) |
|---|---|---|---|---|
| 0:00.0 | Cold open, hero idles in river (lvl4) | Music fade-in | Orient: "MLBB, someone strong" | Lowest-risk hook frame; calm before storm |
| 0:00.7 | **Beat drop** | Music hits full | Body sync / dopamine prime | Anchor track to frame 1 |
| 0:00–0:08 | Push into first teamfight (Iron Body) | In-game pan | First reward fast | Front-load value, kill the scroll |
| ~0:08.5 | **Masked cut → Match B** | Hidden under VFX | (unaware) | Jump to next highlight, hide seam |
| 0:08 | Big ult ring + item toasts | — | "It's popping off" | Density = focus |
| ~0:16 ⟂ | **Masked cut → Match C** | Hidden | (unaware) | Reset to fresh fight |
| 0:16–0:27 | Sustained teamfight | Punch-in | Stay locked | Keep peak energy |
| ~0:27 ⟂ | **Masked cut** | Hidden | — | New clip |
| ~0:43.5 ⟂ | **Masked cut → Match D** | Hidden | — | New clip |
| 0:48 | "Ultimate" + "Iron Body" + 170g | — | Anticipate kill | Build to payoff |
| **0:50.5** | **"Kill" + "Immune" banner** (peak) | **Punch-in ~1.25x** | **Payoff dopamine hit** | Climax of D; densest VFX |
| ~0:52 ⟂ | **Masked cut → Match E** | Hidden inside VFX glow | (unaware) | Cut on the flash = invisible |
| 0:53–0:70 | New fight, score 22v28 | — | Fresh stakes | Variety, avoid fatigue |
| ~0:70.5 ⟂ | **Masked cut → Match F** | Hidden | — | New clip |
| 0:79 | Teamfight | Punch-in | Reward | Sustain |
| 0:90–0:92 | Dense fight (Ring of Vitality buy) | Punch-in | Reward | Sustain |
| ~1:01.4 ⟂ | **Masked cut** | Hidden | — | New clip |
| ~1:41.5 ⟂ | **Masked cut → Match G** | Hidden | — | Final clips |
| 1:09–1:55 | Continued kill clips | Punch-in beats | Sustain to end | No decay; keep watch-time high |
| 1:55.7 | Cut to black, **audio stops** | Hard cut | Pattern interrupt → "it's over" | Force a decision: follow or leave |
| 1:55.7–1:58.7 | End card `@mark9m_` | Static | Read handle | **Convert view → follow** |

## Hooks / rewards / climax / CTA
- **Hook:** 0:00–0:08 cold open + 0:00.7 beat drop.
- **Micro-rewards:** every "Kill"/banner/damage-number burst (≈ every 8–11 s, one per clip).
- **Climax:** 0:50.5 "Kill + Immune" — densest VFX + on-beat punch-in.
- **CTA:** 1:55.7 silent black end card with searchable `@mark9m_`.
- **No loop seam** — ending is a hard stop, optimized for *follow*, not *replay*.
