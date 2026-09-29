---
name: scos-mission-control-ui
description: Build and evolve premium operator-first Mission Control surfaces over HAIOS and SCOS read models. Use when designing or extending Control Center pages, operator dashboards, skills registries, evidence browsers, approvals, runs, or system-currentness views.
---

# SCOS Mission Control UI

## Purpose
Create a calm, premium mission-control interface that helps a Human answer five questions quickly:
1. What is happening now?
2. What changed?
3. What requires attention?
4. What evidence supports the state?
5. What can the Human safely do next?

## Core Boundary
- UI is presentation and bounded human input only.
- Hermes remains Primary Operator.
- HAIOS remains governance, currentness, approval, and evidence authority.
- SCOS remains deterministic media, telemetry, provenance, and learning authority.
- Never create UI-only authority, hidden auto-actions, canonical state, or a second control plane.
- UNKNOWN, STALE, UNAVAILABLE, DEGRADED, EMPTY, and ERROR are distinct states.

## Information Architecture
Preferred top-level surfaces:
- Overview — current posture, attention queue, currentness, recent activity.
- Runs — execution context, run history, activity, evidence links.
- Skills — searchable capability registry, routing metadata, quality signals, provenance.
- Approvals — explicit Human decision context; actions remain governed and can be disabled.
- Evidence — discoverable evidence artifacts with provenance and timestamps.
- Systems — source identity, version, branch, worktree, service/bridge posture.

## Premium UX Principles
- Mission control, not a generic analytics dashboard.
- One primary signal and restrained neutrals; avoid rainbow status colors.
- Strong visual hierarchy; reduce visual competition and redundant chrome.
- Show overview first, then allow drill-down.
- Make status semantics visible without making the UI noisy.
- Prefer compact information density for tools and operational surfaces.
- Every important panel answers: status, evidence, risk/attention, next action.
- Use empty, unavailable, degraded, error, blocked, and loading states deliberately.
- Never display stale or demo values as live.
- Use design-system components rather than native controls.
- Mobile responsive behavior is required; information hierarchy must survive narrow screens.

## Skills Surface Requirements
A Skills page should make capabilities useful, not merely list files:
- search/filter by name, source, trigger/purpose, and capability domain;
- show source/provenance;
- show routing metadata quality;
- show whether core rules/output contract exist;
- expose references/scripts only as metadata until explicitly opened;
- never run third-party skill scripts from the UI by default;
- do not infer promotion from usage.

## Evidence Surface Requirements
- Show artifact identity/path/category/time and evidence state.
- Evidence is discoverable here; qualification authority remains HAIOS.
- Make source mismatch, stale state, and UNKNOWN visible.
- Avoid dumping raw secrets, argv, credentials, or unrestricted filesystem data.

## Approval Surface Requirements
- Present exact goal/version/artifact context when available.
- Show why approval is required.
- Never use a local boolean or visual click as durable approval.
- Mutation actions stay disabled until governed HAIOS approval is available.
- Replayed, expired, stale, or UNKNOWN approvals must not become executable state.

## Verification Requirements
- Design truth states before happy-path polish.
- Test UI against real read-model contracts.
- Prefer read-only first.
- Record source commit/head, observed_at, schema version, and correlation identifiers.
- Use focused tests before broad regression.
- Treat browser screenshots as presentation evidence, not authority evidence.

## Required Output for New Surfaces
1. User flow
2. Screen sections
3. Panel contracts
4. Backend-state → UI-state mapping
5. Empty/error/blocked/UNKNOWN states
6. Operator actions and authority boundary
7. Data provenance
8. Acceptance criteria
9. Test/evidence plan

## Anti-Patterns
- Dashboard as a wall of charts.
- Hidden automation or auto-refresh that mutates state.
- Fake success.
- DEMO data mixed into LIVE state.
- UI state used as canonical state.
- Approval buttons that directly authorize execution.
- Duplicate backend/telemetry/evidence stores.
- Third-party skill execution without explicit governance.
