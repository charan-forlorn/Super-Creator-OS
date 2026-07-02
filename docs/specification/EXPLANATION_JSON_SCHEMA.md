# Explanation JSON Schema

Status: descriptive reference only

## Purpose

This document describes the JSON shape that commercial Stage 4.1 reports may
reference when they cite explanation-style knowledge evidence. It is descriptive
only. It adds no runtime validation dependency, changes no Stage 3.7 or Stage
3.8 behavior, and does not redefine certified lower-layer contracts.

## Descriptive Shape

Explanation-like JSON produced by certified knowledge layers is expected to be a
plain object with stable, JSON-safe fields such as:

```json
{
  "schema_version": 1,
  "explanation_type": "run",
  "title": "string",
  "summary": "string",
  "supporting_events": [],
  "references": [],
  "confidence": {
    "level": "complete",
    "present": 0,
    "expected": 0,
    "missing": []
  }
}
```

Commercial reports do not consume lower-layer explanation engines directly.
They may only consume explanation-derived facts after those facts have been
projected through the Stage 3.9 `KnowledgeService` public view models.

## Error Shapes

Error objects from certified knowledge layers are deterministic JSON-safe
objects with an `error` discriminator and fields appropriate to that layer.
Stage 4.1 does not expose those raw lower-layer errors. It translates public
access-layer unavailable/not-found states into `CommercialReportError`.

## Runtime Policy

- No JSON Schema library is introduced.
- No runtime validation is added.
- No Stage 3.7/3.8 source file is changed.
- No direct commercial import of explanation, insight, query, or index internals
  is allowed.
