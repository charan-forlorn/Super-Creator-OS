# discovered_skills/

Designated home for **legacy / discovered / experimental skills** that are not (yet)
part of the active set in `skills/`. The architecture references this repository as the
place where older or auto-discovered skills live; this folder makes that contract real.

## Status

- **Currently empty** (no legacy skills migrated yet) — this is expected.
- Active, in-use skills remain under `skills/` (orchestrator, storytelling, video-editor,
  qa-reviewer, retention-expert, social-media-manager).

## Convention (mirror of `skills/`)

```
discovered_skills/
└── <skill-name>/
    └── SKILL.md          ← same shape as an active skill
```

## Rules

- **Read-only to the Orchestrator.** A discovered skill is reference material; it does not
  run in the live workflow until it is *promoted* (moved into `skills/`) after review.
- **Promotion:** move `discovered_skills/<name>/` → `skills/<name>/`, then wire it into the
  Orchestrator workflow in `skills/orchestrator/SKILL.md`. Until promoted, the Orchestrator
  may read it for ideas but must not depend on it.
- No code lives here — these are markdown skill specs only (no new runtime dependency).
