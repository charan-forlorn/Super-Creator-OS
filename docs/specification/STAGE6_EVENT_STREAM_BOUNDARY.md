# Stage 6.4 Event Stream / UI Sync Boundary

## What Stage 6.4 is

A local-only, deterministic **snapshot** layer sitting between the Stage 6.3
durable SQLite WAL state store and future real-time operator surfaces:

```
SQLiteStateStore              (Stage 6.3, durable, on-disk)
      |
StateRepository / build_state_snapshot()   (Stage 6.3)
      |
event_stream_snapshot.project_durable_event() /
  build_event_stream_snapshot_from_durable_events()   (Stage 6.4)
      |
EventStreamSnapshot                                    (Stage 6.4)
      |
ui_state_sync.build_ui_state_sync_snapshot()           (Stage 6.4)
      |
UIStateSyncSnapshot                                    (Stage 6.4)
      |
Control Center static/local sync panels                (Stage 6.4 frontend, mock data)
```

Every step above is a pure function call over already-durable, caller-supplied
data. Nothing in this chain opens a socket, starts a server, spawns a thread,
or waits on I/O that isn't a direct SQLite read.

## Why this is not real-time transport

Stage 6.4's job is to answer: *can Control Center read durable local state,
project it into deterministic event batches, and summarize it for a UI panel
— without any live transport?* Building the transport (WebSocket/SSE/polling)
before this snapshot contract exists would mean streaming an undefined shape.
The contract has to be stable first.

## Why WebSocket / SSE / polling are deferred

- **WebSocket / SSE** require a running server process accepting connections.
  Stage 6 so far is local-first and process-less by design (Stage 6.2's
  backend is a command API, not a listening socket). Introducing a socket
  server is a materially different trust boundary and is out of scope until
  a stage explicitly approves it.
- **Polling / timers** require reading the system clock to decide "when to
  check again." Every Stage 6.4 module is built with a **no-clock** guarantee
  (`generated_at` and staleness thresholds are always caller-supplied) so
  that outputs stay deterministic and testable without timing flakiness.
  Polling would break that guarantee at the very first line of code.
- **Real adapter dispatch** (actually running an AI agent) is a separate,
  much higher-trust capability gated behind operator approval flows that
  Stage 6.4 does not touch.

## What Stage 6.4 prepares for Stage 6.5+

- A stable, versioned `EventStreamSnapshot` / `UIStateSyncSnapshot` shape
  that a future real transport (whatever it turns out to be — polling,
  SSE, WebSocket, or something else) can serialize over the wire without
  redesigning the underlying data model.
- A frontend contract (`event-stream-types.ts`, `ui-state-sync-types.ts`)
  and mock-data-driven panels that can be pointed at a real backend endpoint
  later by swapping the data source, not by rewriting the components.
- Clear separation between "durable state" (Stage 6.3), "event projection"
  (Stage 6.4 backend), and "UI presentation" (Stage 6.4 frontend) so that
  adding a transport in a later stage only touches one seam.

## Explicit non-goals for this stage

Not WebSocket. Not SSE. Not polling. Not a background worker. Not real AI
adapter dispatch. Not browser automation. Not GUI automation. Not cloud/SaaS
behavior. Not a Next.js API route, route handler, or middleware.
