# AI Business Production Capability Contract R1

**Status:** IMPLEMENTED IN ISOLATED WORKTREE
**Scope:** Phase 1 capability normalization

## Purpose

Define one provider-neutral vocabulary for AI/media capabilities and one deterministic representation of executable runtime identity. This is a contract layer, not an orchestrator and not an authorization system.

## Canonical capabilities

`generate_text`, `generate_image`, `edit_image`, `generate_video`, `image_to_video`, `generate_voice`, `generate_music`, `transcribe`, `remove_background`, `upscale`, `analyze_media`, `edit_video`, `compose_video`, `render_video`.

## Capability availability

`READY | PARTIAL | ADAPTER_ONLY | EXTERNAL | LOCAL_NO_MODEL | PLANNED | BLOCKED | UNKNOWN`.

`READY` means the descriptor claims readiness; it is not by itself qualification evidence.
## Route admission

A capability candidate is eligible only when all of these are true:

`availability=READY`
`costClass` is explicitly allowed
`currentness=CURRENT`
`health=HEALTHY`
`qualification=QUALIFIED`
`licence=ALLOWED`
`hardware=FIT`
`evidenceComplete=true`

Any unknown or disallowed condition returns a deterministic rejection reason. The result has no `authorized` field and therefore cannot create execution authority.

## Runtime identity

Media execution dependencies are represented by `RuntimeToolIdentity`:

`tool name + absolute path + version + resolution state`.

Unresolved identity is `UNKNOWN`. Different absolute paths are different identities even when the executable filename is the same.

## Governance boundary

Capability discovery and route evaluation remain descriptive. HAIOS retains authority; Hermes remains the operator; SCOS owns production state. This contract intentionally performs no network probes, subprocess execution, configuration mutation, provider switching, spending, or publication.

## Phase 2 handoff

The next router increment may consume these pure contracts to evaluate real provider candidates and produce an evidence-bound route decision record. It must preserve deny-first admission and fail-closed semantics.
