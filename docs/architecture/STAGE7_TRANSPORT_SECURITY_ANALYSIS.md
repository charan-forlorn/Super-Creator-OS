# Stage 7 Transport Security Analysis

Stage: 7.5 - Read Surface Transport Decision / Local UI Sync Activation Gate.

## NO_LIVE_TRANSPORT Security Posture

`NO_LIVE_TRANSPORT` is the lowest-risk option because it introduces no
listener, browser runtime transport, localhost route, timer, background worker,
or network dependency. The Stage 7.4 deterministic static/mock fallback remains
the active behavior.

Security benefits:

- no new input boundary
- no new route or listener exposure
- no browser-origin risk
- no transport dependency risk
- no live data exposure path
- no command execution or adapter dispatch path

Operational benefits:

- deterministic outputs remain replayable
- failures are visible through existing read models and tests
- rollback requires no state migration

## WebSocket Risk Analysis

WebSocket is not approved for implementation in Stage 7.5.

Risks if considered later:

- persistent bidirectional channel increases attack surface
- origin and authentication rules must be explicit
- stale reconnect behavior can mislead operators
- message schema drift can create hidden coupling
- local listener exposure must be strictly localhost-only
- command or adapter state must never be mutated through the read channel

Required future controls:

- operator approval
- localhost-only bind
- authentication and origin review
- deterministic message schema
- frontend recovery and degraded-state tests
- fallback and kill-switch tests
- security scan before activation

## SSE Risk Analysis

Server-Sent Events and EventSource are not approved for implementation in
Stage 7.5.

Risks if considered later:

- long-lived HTTP stream still creates an input and exposure boundary
- origin, auth, and CSRF assumptions must be reviewed
- stale or disconnected streams can present old state as current
- retry behavior must be bounded and visible
- stream payloads could expose audit or approval details if not scoped

Required future controls:

- operator approval
- localhost-only HTTP route
- auth, CSRF, and origin review
- deterministic event schema
- explicit stale-state UI
- fallback and rollback tests
- security scan before activation

## Polling Risk Analysis

Polling is not approved for implementation in Stage 7.5.

Risks if considered later:

- repeated HTTP reads can create local load and noisy logs
- polling cadence can hide stale state or race with file updates
- route exposure still requires auth and origin review
- timer loops can create nondeterministic frontend behavior
- repeated reads must not mutate stores or dispatch work

Required future controls:

- operator approval
- bounded cadence
- localhost-only route
- auth and CSRF review
- stale-state and backoff behavior
- static fallback
- security scan before activation

## Localhost-Only Requirements

Any future transport must:

- bind only to localhost
- reject remote origin assumptions
- treat all route or listener input as untrusted
- expose only approved read projections
- avoid direct frontend SQLite access
- preserve local-first operation
- avoid cloud, SaaS, payment, CRM, customer portal, and external network
  behavior

## Origin and CSRF Considerations

Any future HTTP route must document and test:

- allowed origins
- CSRF posture
- method constraints
- read-only behavior
- error behavior for unknown origins
- no credential or secret exposure

## Data Exposure Risks

Read projections can include command, approval, audit, health, drift, and
activity evidence. A future transport must minimize payloads and must not
expose secrets, environment values, private paths beyond approved local
references, raw audit internals beyond approved views, or adapter credentials.

## Audit and Logging Expectations

Stage 7.5 does not create audit entries because it does not mutate runtime
stores. Future implementation stages must record approval evidence and
activation decisions without weakening append-only audit behavior.

Logs must never include secrets, credentials, tokens, cookies, or private
environment values.

## Dependency Risk

Stage 7.5 adds no runtime dependencies and uses Python stdlib only.

Future transport implementation must justify any dependency addition, prove it
is required, document maintenance and security risk, and update verification
commands.

## Rollback and Kill-Switch Expectations

Future transport implementation must include:

- a documented disable path
- single-stage revert plan
- static/mock fallback restoration
- tests proving transport-off behavior
- security scan evidence after rollback

## Final Stage 7.5 Recommendation

The Stage 7.5 recommendation is `NO_LIVE_TRANSPORT`.

WebSocket, SSE, and polling remain forbidden until a later explicit
implementation stage names the transport, approves the files, adds controls,
passes tests, and preserves Stage 7.4 fallback.
