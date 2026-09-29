# TypeSafe AI / Jev Decision Advisor

## Correct technology identity
TypeSafe AI's Jev is a System One decision model, not a media engine.
The current API exposes one typed evaluation endpoint:
POST https://api.typesafe.ai/v1/systemone

Jev returns typed judgments such as Choice, Score, and Noul, with probabilities
and confidence for applicable answer types. TypeSafe's workflow evaluations
explicitly advocate decomposing automation into code-enforced rules plus
narrow model judgments.

## SCOS role
Jev is an optional Decision Advisor between Media Evidence and EditPlan.
It must never replace deterministic media analysis or RIFE/FFmpeg execution.

## Smooth+ example
Deterministic gate:
- source is local and verified
- duplicate/cadence signal exceeds threshold
- source is CFR
- scene cuts are known
- output can be temporally verified
- RIFE executable/model are present

Jev judgment:
- preserve
- smooth_plus
- quality

Jev score:
0–3 smoothness-need rubric.

Promotion:
- confidence >= 0.85
- Choice = smooth_plus
- deterministic gate = PASS
- temporal QA = PASS
- visual/SSIM thresholds = PASS

Otherwise: REVIEW or PRESERVE.

## Runtime safety
- No key = UNAVAILABLE, never a fabricated decision.
- 401/422 = fail closed, no retry.
- 429/529 = bounded retry only inside the adapter.
- API output is evidence/advice, not authority.
- Human remains authoritative for publication or irreversible actions.

## Current machine
TYPESAFE_API_KEY is absent, so the adapter is installed and tested but not live-called.
