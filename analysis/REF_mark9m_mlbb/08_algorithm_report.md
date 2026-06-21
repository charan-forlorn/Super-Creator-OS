# 08 · Algorithm Analysis (Phase 7)

Platform: **TikTok** (confirmed by vid tag, watermark, end card). Note the **16:9
landscape** delivery is off-spec for TikTok's 9:16 feed — analyzed as a risk below.

## Scroll-stop factors (first 1–2 s)
| Factor | Present? | Effect |
|---|---|---|
| Motion in frame 1 | ✅ hero + ambient VFX | Eye-catch |
| Beat drop at 0.7 s | ✅ | Audio hook syncs thumb-pause |
| Recognizable game UI | ✅ MLBB HUD | Instant relevance to MLBB audience |
| Text hook / question | ❌ none | **Missed lever** (see Gap) |
| Bright color contrast | ✅ neon on green | Thumbnail/feed pop |

## Replay drivers
- Dense fights are visually unparseable in one pass → some rewatch to "see the play".
- **BUT** hard silent stop discourages auto-loop. Net replay = **moderate-low** (by design).

## Share drivers
- "Look how cracked this player is" status-share.
- Rising kill score = screenshot/clip-worthy flex.
- Hero-main identity ("this is our hero") → in-group sharing.

## Save drivers
- Players save for **inspiration / build reference** (items visible: Magic Ring, Ring of
  Vitality) and to study combos at real speed.
- Music could drive save **if** it were a trending sound (unknown — see Gap).

## Comment drivers
- Score/skill provokes "what rank?", "hero build?", "what's the song?".
- "What's the song" is a known comment-farm; the continuous unobtrusive track invites it.

## Follow drivers
- The entire close is engineered for follow: silent black + searchable `@mark9m_`.
- Consistency signal: same hero/style implies a feed of more of the same.

## Platform optimization scorecard
| Lever | State | Grade |
|---|---|---|
| Hook < 2 s | Yes (cold open + drop) | A |
| Watch-time pacing (≤11 s reward gap) | Yes | A |
| Native sound usage | Continuous bed | B (unknown if trending) |
| Aspect ratio fit | **16:9, not 9:16** | **D — biggest algo leak** |
| On-screen text/keywords | None | C (hurts search + accessibility) |
| Loop/seamless end | Hard stop | B (great for follow, weak for replay) |
| CTA | Strong end card | A |
| Caption/hashtags | N/A (not in file) | — |

## Algorithmic verdict
The *editing* is algorithm-aware (hook, pacing, CTA all dialed). The *packaging* leaks:
**landscape 16:9 on a vertical feed** leaves ~45% of the screen unused and is the single
biggest distribution penalty. Adding a **vertical reframe + a text hook + trending sound**
would likely move this from "good" to "viral-capable" without touching the core edit.
