# JAF Evaluation — 2026-09-27

## Identified technology
JAF = Juspay Agent Framework.

JAF describes itself as a type-safe functional agent framework built around
immutable RunState, composable policies, and provider-isolated side effects.
Its Python distribution also supports MCP and agent-as-tool patterns. citeturn204182search0turn204182search6turn204182search8

## Relevance to SCOS
Useful:
- immutable run state
- typed tool boundaries
- deterministic/pure core functions
- effects isolated at the edge
- hierarchical agent-as-tool composition

Already covered by SCOS/Hermes architecture:
- explicit command/event contracts
- deterministic Python workers
- evidence packets
- operator approval boundaries
- Hermes as orchestration layer

## Adoption decision
DO NOT add JAF as a runtime dependency.

Reason:
- SCOS already has equivalent contract/evidence boundaries.
- JAF would introduce a second agent runtime and another operational state model.
- Current repository adoption signals are small (GitHub page showed 12 stars at research time).
- The highest-value JAF ideas can be implemented natively in SCOS without runtime coupling. citeturn204182search0

## Adopted principles
The SCOS media pipeline applies:
immutable evidence snapshots, typed dataclasses, side effects at subprocess/tool
edges, and structured run packets.
