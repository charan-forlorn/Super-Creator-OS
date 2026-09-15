# AI Business Production Capability Normalization R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish one vendor-neutral capability contract and deterministic runtime identity for SCOS media/AI execution, preserving existing edit-provider behavior while creating the seam for R6 capability routing.

**Architecture:** Extend `@haios/ai-providers` with canonical capability descriptors, provider identity, cost/licence/health/currentness metadata, and immutable route candidates. Add a separate runtime identity module in `@haios/media-engine` so executable dependencies are represented by verified identities rather than guessed PATH names. Do not implement live media routing, new model providers, or provider mutation in this increment.

**Tech Stack:** TypeScript, Zod, Vitest, existing SCOS workspace packages.

**Spec:** Current approved architecture direction from the 2026-09-15 AI Business Production System forensic review and the existing HAIOS R6 routing policy.

## Global Constraints
- Preserve existing `AIProvider`, `OfflineProvider`, `OllamaProvider`, `OpenAICompatibleProvider`, and AI edit-plan contracts.
- No live Hermes routing mutation, credential creation, provider login, or paid spend.
- No new orchestrator or second governance plane.
- Unknown cost/currentness/health remains ineligible; normalization must be descriptive only.
- Tests must prove fail-closed classification without claiming provider qualification.
- Source changes occur only in this isolated worktree.

---

### Task 1: Canonical capability contract

**Files:**
- Create: `packages/ai-providers/src/capabilities.ts`
- Modify: `packages/ai-providers/src/index.ts`
- Test: `packages/ai-providers/tests/capabilities.test.ts`

**Interfaces:**
- Produces `CapabilityName`, `CapabilityDescriptor`, `ProviderIdentity`, `CostClass`, `CapabilityAvailability`, and `CapabilityCandidate`.
- `CapabilityCandidate` represents evidence-backed metadata only; it must not authorize execution.

- [ ] **Step 1: Write failing tests** for canonical capability names, descriptor validation, unknown-cost blocking, and provider identity separation.
- [ ] **Step 2: Run `pnpm --dir packages/ai-providers exec vitest run tests/capabilities.test.ts` and confirm the new tests fail because the module/types do not exist.
- [ ] **Step 3: Implement the minimal Zod-backed types and pure eligibility helper.**
- [ ] **Step 4: Run the focused test and confirm PASS.**
- [ ] **Step 5: Run existing `packages/ai-providers/tests/providers.test.ts` to prove no regression.**
- [ ] **Step 6: Commit `feat: add canonical capability provider contract`.**

---

### Task 2: Runtime identity normalization

**Files:**
- Create: `packages/media-engine/src/runtimeIdentity.ts`
- Modify: `packages/media-engine/src/index.ts`
- Test: `packages/media-engine/tests/runtime-identity.test.ts`

**Interfaces:**
- Produces `RuntimeToolKind`, `RuntimeToolIdentity`, `RuntimeIdentity`, and `compareRuntimeIdentity()`.
- `RuntimeToolIdentity` must include canonical tool name, absolute path, version, and resolution status.

- [ ] **Step 1: Write failing tests** proving absolute-path identity is distinct from PATH aliases and unresolved tools are `UNKNOWN` rather than usable.
- [ ] **Step 2: Run the focused test and confirm RED.**
- [ ] **Step 3: Implement pure runtime identity normalization/comparison without probing the host or mutating environment.**
- [ ] **Step 4: Run focused tests and confirm GREEN.**
- [ ] **Step 5: Run existing `packages/media-engine/tests/cache.test.ts` and `preview-proxy.test.ts` for regression.**
- [ ] **Step 6: Commit `feat: normalize media runtime identity`.**

---

### Task 3: R6-compatible route candidate model

**Files:**
- Create: `packages/ai-providers/src/routing.ts`
- Modify: `packages/ai-providers/src/index.ts`
- Test: `packages/ai-providers/tests/routing.test.ts`

**Interfaces:**
- Produces `RouteCandidate`, `RouteRejectionReason`, and `evaluateRouteCandidate()`.
- Inputs: capability, provider identity, model identity, cost class, health/currentness/qualification states, licence state, hardware fit, evidence completeness.
- Output is a pure admission classification; no network access, subprocess execution, config writes, or provider switching.

- [ ] **Step 1: Write failing tests** covering a fully eligible candidate, unknown cost rejection, stale currentness rejection, unqualified provider rejection, and missing evidence rejection.
- [ ] **Step 2: Run focused tests and confirm RED.**
- [ ] **Step 3: Implement deterministic deny-first admission evaluation.**
- [ ] **Step 4: Run focused tests and confirm GREEN.**
- [ ] **Step 5: Run both ai-provider test suites together.**
- [ ] **Step 6: Commit `feat: add fail-closed capability route admission`.**

---

### Task 4: Package and documentation reconciliation

**Files:**
- Modify: `packages/ai-providers/package.json`
- Modify: `packages/media-engine/package.json`
- Create: `docs/architecture/AI_BUSINESS_PRODUCTION_CAPABILITY_CONTRACT_R1.md`
- Test: existing package typecheck/build commands

- [ ] **Step 1: Update package scripts only if required to expose focused verification consistently.**
- [ ] **Step 2: Document the canonical capability vocabulary, boundary between selection and authority, and current non-goals.**
- [ ] **Step 3: Run TypeScript typechecks/builds for both packages.**
- [ ] **Step 4: Run the full focused regression set for both packages.**
- [ ] **Step 5: Verify the worktree contains only intended changes.**
- [ ] **Step 6: Commit `docs: define capability contract r1`.**

---

### Task 5: Verification and handoff

**Files:**
- No production-source changes expected.
- Evidence: worktree-local verification output.

- [ ] **Step 1: Run all Task 1–4 focused tests from the isolated worktree.**
- [ ] **Step 2: Run package typechecks/builds.**
- [ ] **Step 3: Record exact HEAD, working-tree state, test totals, and any remaining blockers.**
- [ ] **Step 4: Confirm no Hermes live route/configuration was modified.**
- [ ] **Step 5: Prepare Phase 2 handoff: capability router can consume these pure contracts without changing governance boundaries.**
