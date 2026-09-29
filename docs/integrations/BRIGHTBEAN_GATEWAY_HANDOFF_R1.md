# Brightbean Gateway Handoff R1

SCOS is a producer, not the social execution boundary.

## Flow

SCOS:
1. produce content/media
2. validate artifact
3. hand off an immutable or verified artifact reference
4. let Hermes decide schedule/publish
5. receive verification/result state

## Boundary

SCOS must not store or directly use the Brightbean API key.
SCOS must not call Facebook/Instagram/TikTok/YouTube publish APIs directly when the Brightbean gateway path is available.

## Media

Use Brightbean media tools after artifact validation.
Large assets use the gateway large-upload flow.
Publication success is not inferred from upload success; Hermes must read back the post state.

## Governance

Draft = safe preparation.
Schedule/publish = explicit execution intent.
Post-publication state = Brightbean read-back evidence.
