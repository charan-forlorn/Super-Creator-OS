# AI Business Production Adaptive Capability Router R1

## Purpose

Phase 2 turns the Phase 1 capability contract into a deterministic routing decision engine without transferring authority from HAIOS.

The router answers only:

> Given a requested capability, which currently evidenced provider/model is eligible under the supplied HAIOS governance evidence and machine observation?

It does not grant authority, approve spend/publication, or execute work.

## Authority boundary

```text
HAIOS
  ├─ currentness
  ├─ qualification
  ├─ licence
  ├─ hardware policy
  ├─ allowed cost classes
  └─ evidence completeness / references
       ↓
Adaptive Capability Router
  ├─ bind governance evidence to provider/model
  ├─ bind machine observation to provider/model
  ├─ reject stale/unknown/unqualified/mismatched candidates
  ├─ rank remaining eligible candidates deterministically
  └─ emit ROUTED or DENIED
       ↓
Hermes / SCOS execution layer
```

Candidate-supplied governance fields are not trusted when HAIOS evidence is present. The router derives currentness, qualification, licence, hardware fit, and evidence completeness from governance input, while health/model presence are bound to machine evidence.

## Route eligibility

A candidate is routable only when all of these are evidenced:

- requested capability matches
- HAIOS governance evidence exists and is complete
- model is observed on the target machine/provider
- specified model version matches observed identity when supplied
- HAIOS currentness is `CURRENT`
- HAIOS qualification is `QUALIFIED`
- HAIOS licence is `ALLOWED`
- HAIOS hardware state is `FIT`
- candidate cost class is explicitly allowed by HAIOS
- machine/provider health is `HEALTHY`
- evidence references are present

No eligible candidate produces `DENIED`; the router never silently falls back to an unverified provider.

## Cost policy

The Phase 1 default remains conservative: `local_zero_inference_cost` and `free_keyless` are allowed.

Phase 2 does not hard-code this policy into the router. HAIOS can explicitly supply an allowed set, including `free_or_variable` or another supported class, when governance evidence authorizes it.

## Machine evidence

`probeOllamaMachineEvidence()` performs a read-only observation of the local Ollama `/api/tags` endpoint and records model IDs and digests. The probe's `HEALTHY` value is provider API reachability, not proof that every model has passed functional generation benchmarking.

## Verified live observation — 2026-09-16

On the development machine, Ollama was reachable and reported:

- `qwen3:14b` — digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`
- `qwen3:4b` — digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`

A real end-to-end router run intentionally supplied **no HAIOS governance evidence**. Both routes were therefore rejected with `missing_governance_evidence`.

This is the expected fail-closed result: machine presence alone is insufficient to establish production eligibility.

Current Library evidence also does not establish that these two live Ollama models are presently HAIOS-qualified/current. Therefore Phase 2 must not promote them to an authorized production route merely because they are installed and reachable.

## Determinism

Eligible candidates are sorted by descending explicit `priority`, then by stable `providerId:modelId` key. The selected route carries the governance and machine evidence references used to make the decision.

## Non-goals

This increment does not:

- modify Hermes live routing/configuration
- authorize paid providers
- change HAIOS policy or qualification state
- execute model inference
- perform public delivery or publication
- merge or push the feature branch
