# SCOS Skill Pack v1

## 1. Overview
SCOS Skill Pack v1 is a set of 15 markdown-only, reusable skill definitions under `.skills/`. Each `SKILL.md` is a self-contained prompt template usable by ChatGPT (PM/analyst/designer), Claude Code (builder), and Codex (reviewer) — with or without a `/skill` command. The pack encodes the SCOS working principles: contract-first design, deterministic local-first behavior, evidence-based certification, clean Git workflow, stage-gated execution, and no self-approval by builder agents.

## 2. Goals
1. Reduce token usage (exact file scopes, referenced context, compact outputs).
2. Reduce out-of-scope work (every skill carries Anti-Scope-Drift Rules).
3. Improve development quality (evidence gates, independent review, defect verification).
4. Make Stage 6+ development faster while preserving safety and certification quality.

## 3. Skill List
| Skill | Role | Purpose |
|---|---|---|
| scos-project-manager | ChatGPT | Stage control, scope, routing, GO/NO-GO |
| scos-requirement-analyst | ChatGPT | Vague idea → testable requirements |
| scos-system-architect | ChatGPT | Contract-first design before build |
| scos-claude-builder | ChatGPT → Claude | Generate scoped build prompts |
| scos-codex-reviewer | Codex | Defect/regression review, verdict |
| scos-git-safety-gate | Any | Git preflight before build/commit/push |
| scos-test-certifier | Codex/Claude | Evidence-based stage certification |
| scos-defect-verifier | Codex/Claude | Verify defects at HEAD without re-fixing |
| scos-doc-writer | Any | Concise evidence-based documentation |
| scos-control-center-ui | ChatGPT | Operator-first UI/panel design |
| scos-realtime-runtime | ChatGPT | Local-first replayable event runtime design |
| scos-ai-orchestrator | ChatGPT | Multi-agent workflow + fallback coordination |
| scos-token-cost-optimizer | Any | Prompt/stage/test-set compression |
| scos-release-manager | ChatGPT/Codex | Release readiness and safe stage closure |
| scos-commercial-advisor | ChatGPT | Technical stages → monetizable outcomes |

## 4. Skill Routing Matrix
| Situation | Skill(s) in order |
|---|---|
| New vague feature idea | requirement-analyst → system-architect → project-manager |
| Stage kickoff | project-manager → git-safety-gate |
| Build task | claude-builder (prompt) → git-safety-gate → build |
| Build complete | codex-reviewer → (fixes) → test-certifier |
| Old defect list, unknown status | defect-verifier |
| Stage close / release | test-certifier → release-manager → doc-writer |
| New panel / dashboard | control-center-ui (mock-first) → claude-builder |
| Live updates / events | realtime-runtime → control-center-ui → claude-builder |
| Multi-agent workflow broken | ai-orchestrator |
| Prompts/sessions too expensive | token-cost-optimizer |
| "What should we sell/demo?" | commercial-advisor → project-manager |
| Any commit/push decision | git-safety-gate (always) |

## 5. Recommended Workflow for New Stage
1. `scos-requirement-analyst` — refine the idea; stop if verdict is not Ready-for-Architecture.
2. `scos-system-architect` — contracts, state machine, migration risk.
3. `scos-project-manager` — stage plan, scope boundary, agent assignment, acceptance criteria.
4. `scos-doc-writer` — record Stage Plan + Scope Boundary under docs/.
5. Proceed to the build workflow below.

## 6. Recommended Workflow for Claude Code Build
1. `scos-claude-builder` — generate the scoped build prompt from the approved design.
2. `scos-git-safety-gate` — preflight; BLOCKED stops everything.
3. Claude Code executes: inspect listed files → implement numbered tasks → run test commands → emit the Final Report Format.
4. No commit/push; hand the report to review.

## 7. Recommended Workflow for Codex Review
1. `scos-git-safety-gate` — confirm the tree contains only the declared build changes.
2. `scos-codex-reviewer` — diff-scoped review, defect list with file:line, GO/NO-GO.
3. If NO-GO: Required Fixes go back through `scos-claude-builder` (minimal scope), then re-review.
4. If GO: `scos-test-certifier` runs the gate; user authorizes commit with the suggested message.

## 8. Recommended Workflow for UI / Realtime Work
1. `scos-realtime-runtime` — event contract first (JSONL, replayable, fallback mode) if live data is involved.
2. `scos-control-center-ui` — panel contracts, state mapping, empty/error/blocked states, mock data shape.
3. Build mock-first via the Claude Code build workflow; certify the mock stage.
4. Only then wire real events, as a separate scoped stage.

## 9. Recommended Workflow for Token Reduction
1. `scos-token-cost-optimizer` — audit current prompts/stage plans for waste.
2. Apply Prompt Compression and Stage Compression outputs; keep all gates intact.
3. Adopt: exact file scopes, referenced (not pasted) background, Minimal Test Set for iteration, Full Gate Test Set only at certification.
4. Re-audit after each stage series.

## 10. Phase Rollout
**Phase 1 — Core Development Safety:** scos-project-manager, scos-system-architect, scos-claude-builder, scos-codex-reviewer, scos-git-safety-gate, scos-test-certifier, scos-defect-verifier.

**Phase 2 — Control Center Runtime:** scos-control-center-ui, scos-realtime-runtime, scos-ai-orchestrator, scos-doc-writer.

**Phase 3 — Scale / Release / Business:** scos-token-cost-optimizer, scos-release-manager, scos-commercial-advisor, scos-requirement-analyst.
