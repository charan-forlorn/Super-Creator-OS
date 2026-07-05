# AI Agent Adapter Registry Contract (Stage 5.3)

## Registry purpose

Define a static, deterministic catalogue of the five contract-only agent
adapters (`scos/control_center/agent_adapter_registry.py`) that the adapter
simulator uses to look up and recommend an adapter for a given
`AgentAdapterRequest`. The registry describes and selects among adapters;
it never launches, calls, drives, or communicates with any of them, and it
never probes the local environment for installed applications.

## Adapter lookup rules

- `list_adapters() -> tuple[BaseAgentAdapter, ...]` — every registered
  adapter, fixed declaration order: `chatgpt`, `claude_code`, `codex`,
  `hermes`, `manual_clipboard`.
- `list_capabilities() -> tuple[AgentAdapterCapability, ...]` — every
  capability from every adapter, in the same fixed order (8 entries in
  Stage 5.3: 2 each for `chatgpt`/`claude_code`/`codex`, 1 each for
  `hermes`/`manual_clipboard`).
- `find_adapter(agent_name, runtime_type, task_type) -> BaseAgentAdapter | None`
  — the first adapter (fixed order) whose `agent_name()` matches and whose
  declared capabilities cover both `runtime_type` and `task_type`; `None` if
  no adapter matches (never raises).
- `validate_request(request) -> tuple[str, ...]` — empty tuple means valid.
  Combines an adapter-availability check (via `find_adapter`) with the
  matched adapter's own `validate_request`. Allowed-value enforcement for
  each request field already happened in `AgentAdapterRequest.__post_init__`
  — this only checks whether a registered adapter can actually serve the
  request's declared `agent_name` / `runtime_type` / `task_type` triple.

## Deterministic ordering

`create_default_agent_adapter_registry()` builds the registry once from a
fixed-order tuple of adapter instances. `list_adapters()` and
`list_capabilities()` return the same tuple, in the same order, on every
call — no adapter is ever added, removed, or reordered at runtime.

## Recommended routing

`recommend_adapter(task_type, preferred_agent=None) -> BaseAgentAdapter`:

| `task_type` | Primary adapter | Alternate (`preferred_agent`) | Fallback |
| --- | --- | --- | --- |
| `planning` | `chatgpt` | — | `manual_clipboard` |
| `implementation` | `claude_code` | — | `manual_clipboard` |
| `review` | `codex` | — | `manual_clipboard` |
| `audit` | `hermes` | — | `manual_clipboard` |
| `status_update` | `chatgpt` | — | `manual_clipboard` |
| `prompt_build` | `chatgpt` | `claude_code` | `manual_clipboard` |
| `release_gate` | `codex` | `claude_code` | `manual_clipboard` |
| `git_review` | `codex` | — | `manual_clipboard` |
| `manual_handoff` | `manual_clipboard` | — | `manual_clipboard` |

If `preferred_agent` names a valid alternate for the given `task_type` (per
the table above) and that adapter actually declares support for the task,
it is used. Otherwise the primary adapter is used if it supports the task.
If neither is available, or the mapped adapter can't serve the task,
`recommend_adapter` always falls back to `manual_clipboard` — it never
returns `None`.

## Manual fallback behavior

`manual_clipboard` is a full member of the registry (not a special case in
the lookup code) and always declares support for every value in
`ALLOWED_ADAPTER_TASK_TYPES`. This guarantees `recommend_adapter` can always
return a usable adapter, and `find_adapter("manual_clipboard",
"manual_clipboard", <any allowed task_type>)` always succeeds.

## Invalid request handling

- An unknown `agent_name`/`runtime_type`/`task_type`/`delivery_mode` never
  reaches the registry — `AgentAdapterRequest.__post_init__` rejects it with
  `ValueError` at construction time.
- A structurally valid request that no adapter can serve (e.g. a
  `task_type` unsupported by the named `agent_name`/`runtime_type` pair)
  produces a non-empty tuple of problem strings from `validate_request`, and
  the simulator turns that into a deterministic `AgentAdapterError` with
  `error_kind="contract_violation"` — never a raised exception.

## No environment probing rule

The registry and every adapter build their answers purely from in-source,
fixed capability declarations. Nothing in this module reads an environment
variable, checks whether an app/CLI is installed, inspects a process list,
or touches the filesystem/network to "discover" what's available locally.
"Registered" means "declared", not "detected".

## Future real-adapter requirements

A future stage that replaces a contract-only adapter with a real
integration must:

- Keep implementing the full `BaseAgentAdapter` contract (`adapter_id`,
  `agent_name`, `runtime_type`, `capabilities`, `validate_request`,
  `prepare_prompt`, `simulate_send`, `capture_result`) with the same
  deterministic signatures.
- Not change `AI_AGENT_ADAPTER_SCHEMA_VERSION` or any Stage 5.3 model field
  for a compatible upgrade — only add new fields/values additively.
- Keep `manual_clipboard` registered and enabled as the guaranteed fallback,
  even once real dispatch exists for other adapters.
- Introduce any real I/O (network, subprocess, clipboard, GUI) in a clearly
  separated module, never inside `agent_adapter_models.py`,
  `agent_adapter_contracts.py`, `agent_adapter_registry.py`, or
  `agent_adapter_simulator.py` — those four modules stay pure and
  deterministic by contract.
