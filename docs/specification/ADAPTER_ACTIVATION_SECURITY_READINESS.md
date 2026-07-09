# Adapter Activation Security Readiness

Stage: 7.7 - Adapter Activation Preflight Gate.

## Readiness Position

Stage 7.7 is a security and operations readiness check, not an activation
approval. A `GO` result means the local evidence is coherent enough for a
later explicit activation stage to consider next steps. It does not permit
dispatch by itself.

## Required Controls

- Operator approval evidence must be present before any future real dispatch.
- Append-only audit evidence must remain inspectable.
- Manual fallback must remain available.
- Simulator fallback must remain available.
- Secret handling must remain policy-only in Stage 7.7; no secret values are
  accepted or read.
- Rollback must remain manual and explicit.
- Transport boundaries from Stage 7.5 remain in force.
- Stage 7.6 command visibility is read-only evidence, not execution authority.

## Blocked Behaviors

The preflight gate rejects or blocks:

- real adapter dispatch
- live adapter modes
- API or cloud dispatch
- browser or GUI automation
- clipboard automation
- URL or remote path inputs
- credential marker inputs
- subprocess or shell execution
- nondeterministic runtime behavior

## Report Semantics

- `GO`: no blockers or warnings were found. Activation is still deferred.
- `NO_GO`: no blockers were found, but warnings require operator review.
- `BLOCKED`: one or more required controls or safety checks failed.

Regardless of result, `can_activate_now` is `False` and `dispatch_blocked` is
`True`.

## Operator Handoff

Before any later activation stage, the operator must review the preflight
report, confirm Stage 7 closure, confirm security scan evidence, define a
separate real-dispatch contract, and preserve manual override paths.
