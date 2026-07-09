# Stage 8 Transport Security Analysis

Stage 8.1 compares local transport options for future Control Center UI sync.
This analysis does not implement transport.

## Summary

| Option | Security risk | Operational risk | Stage 8.1 recommendation |
|---|---|---|---|
| `NO_TRANSPORT` | Lowest | Lowest | Default approved decision |
| `FILE_SNAPSHOT_REFRESH` | Low | Low | Safest future implementation candidate |
| `LOCAL_HTTP` | Medium | Medium | Allowed later only with stricter local server contract |
| `WEBSOCKET` | High | High | Defer beyond first implementation candidate |
| `SSE_EVENTSOURCE` | Medium-high | Medium-high | Defer until simpler local option is proven |
| `POLLING` | Medium | Medium-high | Defer unless bounded cadence is explicitly justified |

## NO_TRANSPORT

- Locality boundary: no runtime channel is opened.
- Origin / CSRF / local exposure risk: none beyond existing local files.
- Stale data risk: manual refresh can be stale, but the operator controls it.
- Event ordering risk: lowest because evidence is read as snapshots.
- Accidental command execution risk: none if read surfaces stay read-only.
- Adapter dispatch risk: none.
- Secret exposure risk: none introduced.
- Rollback / kill switch requirement: preserve current behavior.
- Operator approval preservation: unchanged.
- Deterministic testability: strongest.

Recommendation: approve as the default Stage 8.1 decision.

## FILE_SNAPSHOT_REFRESH

- Locality boundary: local filesystem only.
- Origin / CSRF / local exposure risk: low; path validation is mandatory.
- Stale data risk: medium; snapshot age must be visible.
- Event ordering risk: low if snapshot versioning is explicit.
- Accidental command execution risk: must remain none.
- Adapter dispatch risk: must remain blocked.
- Secret exposure risk: snapshot content must exclude credentials.
- Rollback / kill switch requirement: revert to no transport.
- Operator approval preservation: snapshots may observe approval state only.
- Deterministic testability: strong.

Recommendation: safest allowed-later implementation candidate.

## LOCAL_HTTP

- Locality boundary: must bind only to an operator-local interface if later
  approved.
- Origin / CSRF / local exposure risk: medium; request forgery and local page
  origin risks require a dedicated contract.
- Stale data risk: medium; response freshness must be visible.
- Event ordering risk: medium; response ordering must be deterministic.
- Accidental command execution risk: route must remain read-only.
- Adapter dispatch risk: must remain blocked.
- Secret exposure risk: no credentials in responses, logs, or reports.
- Rollback / kill switch requirement: local server disabled fallback required.
- Operator approval preservation: route cannot approve or execute.
- Deterministic testability: possible but stricter than file snapshots.

Recommendation: allowed later only after a stricter local server contract.

## WEBSOCKET

- Locality boundary: must be local-only if ever approved later.
- Origin / CSRF / local exposure risk: high because the channel is persistent
  and bidirectional.
- Stale data risk: medium; connection health can mask stale payloads.
- Event ordering risk: high; replay and ordering must be proven.
- Accidental command execution risk: high unless command paths are impossible.
- Adapter dispatch risk: must remain blocked.
- Secret exposure risk: persistent channel must never carry credentials.
- Rollback / kill switch requirement: immediate disconnect and fallback.
- Operator approval preservation: bidirectional messages cannot approve or
  execute.
- Deterministic testability: difficult.

Recommendation: defer beyond first implementation candidate.

## SSE_EVENTSOURCE

- Locality boundary: must be local-only if ever approved later.
- Origin / CSRF / local exposure risk: medium-high; stream exposure and
  origin handling require review.
- Stale data risk: medium; dropped streams must not appear healthy.
- Event ordering risk: medium-high; missed event handling must be proven.
- Accidental command execution risk: lower than bidirectional channels but
  must remain impossible.
- Adapter dispatch risk: must remain blocked.
- Secret exposure risk: stream payloads must exclude credentials.
- Rollback / kill switch requirement: stream disabled fallback required.
- Operator approval preservation: stream is observe-only.
- Deterministic testability: moderate difficulty.

Recommendation: defer until snapshot or local request option is proven.

## POLLING

- Locality boundary: must be local-only if ever approved later.
- Origin / CSRF / local exposure risk: medium; repeated local reads still need
  origin, path, and rate controls.
- Stale data risk: medium; cadence gaps must be visible.
- Event ordering risk: medium; repeated reads must not reorder evidence.
- Accidental command execution risk: must remain none.
- Adapter dispatch risk: must remain blocked.
- Secret exposure risk: responses and logs must exclude credentials.
- Rollback / kill switch requirement: repeated refresh must stop immediately.
- Operator approval preservation: polling can observe only.
- Deterministic testability: harder because cadence can create nondeterminism.

Recommendation: defer unless bounded cadence is explicitly justified.

## Security Conclusion

Stage 8.1 should approve `NO_TRANSPORT` by default. If the operator wants a
future implementation candidate, `FILE_SNAPSHOT_REFRESH_ALLOWED_LATER` is the
lowest-risk first option. `LOCAL_HTTP`, `WEBSOCKET`, `SSE_EVENTSOURCE`, and
`POLLING` require stronger contracts before implementation.
