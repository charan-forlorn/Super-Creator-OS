# Change Control

> Status: Approved (see [DOCUMENT_LIFECYCLE.md](DOCUMENT_LIFECYCLE.md))

Answers: who can change a governing document, when, why, with what impact, and whether review is required. This exists so routing decisions and capability claims change because of evidence — never because of unreviewed preference.

## What counts as a governing document

Documents whose content directly drives model-routing or model-trust decisions: [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md), [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md), [../ai/MODEL_REGISTRY.md](../ai/MODEL_REGISTRY.md), [../ai/QUALITY_GUIDELINES.md](../ai/QUALITY_GUIDELINES.md), and [../evaluation/SCORING.md](../evaluation/SCORING.md). Templates, playbooks, checklists, and examples are not governing documents — they can be edited more freely (still going through normal review per [DOCUMENT_LIFECYCLE.md](DOCUMENT_LIFECYCLE.md)), since they don't themselves decide which model handles production work.

## Who / when / why / impact / review

| Question | Answer |
|---|---|
| Who can propose a change? | Anyone (human or model) doing development work who has a concrete reason. |
| When? | Whenever evidence justifies it — not on a fixed schedule. |
| Why is required? | A stated reason citing evidence (see the evidence chain below) — "it felt right" is not sufficient justification for a governing-document change. |
| Impact | Stated explicitly: which task categories, which models, which downstream documents (e.g. a `ROUTING_RULES.md` change usually implies an `AI_CAPABILITY_MATRIX.md` update too). |
| Review required? | Yes, always, for governing documents — see the evidence chain below. |

## The evidence chain (required for routing changes)

A change to [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) must be justified by this chain, in order:

```text
  Proposed routing rule change
            |
            v
  Capability Matrix update
  (../ai/AI_CAPABILITY_MATRIX.md
   — the rating that justifies the change)
            |
            v
  Benchmark data
  (../benchmarks/<model>/README.md
   — real recorded runs backing the rating)
            |
            v
  Evaluation score
  (../evaluation/SCORING.md
   — the rubric applied to that benchmark data)
            |
            v
  Approve
  (status moves Review -> Approved per
   ../governance/DOCUMENT_LIFECYCLE.md)
```

No step in this chain may be skipped for a routing change: a capability-matrix update without benchmark data behind it stays a judgment-based rating (acceptable for v1, as already noted in [../ai/AI_CAPABILITY_MATRIX.md](../ai/AI_CAPABILITY_MATRIX.md)'s revision history) but cannot by itself justify changing [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md). See [../anti-patterns/BAD_ROUTING.md](../anti-patterns/BAD_ROUTING.md) for what skipping this chain looks like.

## Review gate

A governing-document change moves from Draft → Review → Approved per [DOCUMENT_LIFECYCLE.md](DOCUMENT_LIFECYCLE.md). The Review stage for a governing document specifically requires: the evidence chain above (for routing/capability changes) or an equivalent stated rationale (for registry/quality-guideline changes), reviewed by a model/person other than the proposer — mirroring the second-opinion rule already used for code review in [../ai/ROUTING_RULES.md](../ai/ROUTING_RULES.md) rule 5.
