# Skill: scos-ai-orchestrator

## Purpose
Coordinate ChatGPT (PM/analyst/designer), Claude Code (builder), Codex (reviewer), and the manual clipboard fallback into one gated workflow.

## When to Use
- Setting up the workflow for a new stage across multiple agents.
- A handoff between agents failed, produced mismatched formats, or stalled.
- Deciding which agent should own a task.

## Core Rules
- Builder output must be reviewed by the reviewer; agents never self-approve their own work.
- Every AI task carries: objective, scope, input packet, expected output, and validation gate.
- Handoffs use defined packets — an agent that didn't receive a complete input packet stops and reports.
- Manual clipboard is the guaranteed fallback path when any automated handoff fails.
- One agent, one role per task; no role mixing within a single prompt.

## Required Output
- Workflow
- Agent Responsibility Matrix
- Input Packet
- Output Packet
- Handoff Rules
- Failure Recovery
- Manual Fallback
- Control Center UI Mapping
- Testable Acceptance Criteria

## Prompt Template
```
Act as SCOS AI Orchestrator.
Task: <stage or workflow to coordinate>.
Produce the Required Output. Responsibility Matrix as agent × phase table.
Packets as field lists. Every handoff names its validation gate and its
manual-fallback equivalent.
```

## Anti-Scope-Drift Rules
- Orchestrate only the given task; do not redesign the agents' internal skills.
- No new agents or tools introduced without user approval.
- Workflow changes must not bypass the review gate or Git safety gate.

## Token-Saving Rules
- Packets carry references (paths, commit hashes) instead of pasted content.
- Each agent prompt contains only its own role's context, not the full history.
- Reuse the standard skill prompts (builder/reviewer/certifier) rather than restating rules.
