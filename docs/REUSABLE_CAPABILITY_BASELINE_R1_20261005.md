# SCOS Reusable Capability Baseline R1

Date: 2026-10-05
Scope: C:\Workspace\super-creator-os
Authority model: HAIOS remains the execution authority. This document is a capability handoff index, not an authority grant.

## 1. Reusable capability lanes

| Capability | Canonical boundary | Consumer | Allowed use | Authority boundary |
|---|---|---|---|---|
| HAIOS creative job bridge | `integrations/haios_bridge/bridge.py` / `HAIOS_SCOS_CREATIVE_JOB_V1` | HAIOS, n8n | Validate and execute bounded local creative jobs; return artifact + provenance | Only `dry_run` / `local`; no external publishing, credentials, payment, or authority expansion |
| Local video analysis/edit helpers | `integrations/mcp/scos_video_mcp.py` | Local development only | Probe, analysis, extraction, bounded local media operations | **Not exported to external consumers yet**; raw path surface requires sandbox/allow-list hardening before network or cross-project exposure |
| Commercial/manual production artifacts | `scos/commercial/*` | Revenue pipeline, n8n | Build deterministic local handoff, offer, QA, delivery, and readiness artifacts | Manual-only; no send, payment, CRM sync, or external customer action |
| Learning / memory | `integrations/learning/*` | SCOS, HAIOS | Persist validated learning/telemetry and retrieve recommendations | Canonical writes remain inside existing guarded paths; no second memory authority |
| Core render / media | `scos/render/*`, `integrations/adapter/*` | SCOS, downstream artifact consumers | Produce validated media artifacts | Rendering produces artifacts; publication remains downstream and governed |
| Local AI provider contracts | `packages/ai-providers/*` | Desktop / HAIOS integration | Capability discovery, route qualification, local provider execution seams | Route decisions are non-authorizing; qualification evidence is required by the governance layer |
| Project / command / timeline model | `packages/project-model`, `packages/command-system`, `packages/timeline` | Desktop / future adapters | Reuse deterministic project mutations and timeline semantics | Mutations remain inside CommandBus / governed app boundary |

## 2. Recommended consumer paths

### n8n
Use the HAIOS creative job bridge as the stable contract boundary.

```
n8n
  -> HAIOS job request
  -> integrations/haios_bridge/bridge.py
  -> SCOS local pipeline
  -> artifact + QA/provenance
  -> n8n consumes result
```

Do not call SCOS internals directly from n8n when the bridge contract is sufficient.

### BrightBean
SCOS must produce and validate media artifacts only.

```
SCOS render
  -> validate artifact
  -> HAIOS execution/evidence boundary
  -> BrightBean gateway
  -> explicit governed delivery
```

SCOS does not receive BrightBean credentials and does not become the publishing authority.

### Revenue pipeline
Use the deterministic commercial/manual artifact layer.

```
SCOS production
  -> QA
  -> delivery / offer / readiness artifacts
  -> Revenue Ops / n8n
  -> human-controlled customer action
```

External communication, payment, acceptance, and customer execution remain outside this capability package.

## 3. Explicitly excluded from this baseline

- Public production deployment.
- External publishing.
- Credential activation or rotation.
- Payment or billing execution.
- Customer database/CRM synchronization.
- Network exposure of the local MCP raw-path media surface.
- Creation of a second orchestration or authority layer.
- Promotion of machine capability observation into authorization.

## 4. Closure invariant

Consumers should depend on the narrowest existing boundary that satisfies the need:

`n8n -> HAIOS bridge -> SCOS`

`BrightBean -> HAIOS -> validated SCOS artifact`

`Revenue Ops -> deterministic SCOS commercial artifacts`

No consumer should import deep implementation modules merely to bypass an existing contract.

## 5. Verification expectation

A capability may be treated as reusable only when:

1. current source bytes are reconciled;
2. focused tests and the current regression population pass;
3. build/typecheck passes where applicable;
4. no authority boundary is widened;
5. the handoff contract identifies inputs, outputs, provenance, and failure behavior.

This file records the intended reusable boundary; it does not claim external deployment qualification.
