# Repository Intelligence — Rules for AI Agents

> **Status:** ACTIVE (Phase 2.8). How a future AI agent (Claude Code or any LLM) should
> **explore, verify, and reason** about this repository so it produces trustworthy answers.
> Binds with `TRACEABILITY_STANDARD.md`.

---

## 1. Search order (cheapest-authoritative first)

> **⚠️ SUPERSEDED (Phase 2.9 reconciliation, additive — nothing removed below).** The
> canonical retrieval order is now defined **only** in
> [`KNOWLEDGE_RETRIEVAL.md`](KNOWLEDGE_RETRIEVAL.md) §1
> (`Authority → Evidence → Decision → Capability → Repository(verify) → Historical →
> External`). The list below is retained for historical compatibility but is **no longer
> authoritative for retrieval sequencing**; where the two differ, `KNOWLEDGE_RETRIEVAL.md`
> wins. This document remains authoritative for agent etiquette, verification, confidence
> scoring, and stale-evidence detection (§3–§7).

1. **Glossary** (`_knowledge/GLOSSARY.md`) — resolve every term before using it.
2. **Capability Registry** (`_knowledge/CAPABILITY_REGISTRY.md`) — find the capability,
   its owner, maturity, and the `EV`/`DD` that ground it.
3. **Registers** (`EVIDENCE_REGISTER`, `DECISION_REGISTER`) — follow the cited IDs.
4. **Evidence Ledger** (`_evidence/EVIDENCE_LEDGER.md`) — narrative context behind an `EV`.
5. **Repository itself** — the cited paths in `integrations/**`, `skills/**`, `memory/**`.
6. **Audit reports** (`project_audit/*`) — rich but **dated 2026-06-22 / lineage
   h1-foundation**; treat as historical, re-verify before asserting as current.

Never answer a "what is true now" question from the audits or ledger alone — confirm at
the repository (step 5).

## 2. Priority / authority rules

- Apply `AUTHORITY_MODEL.md`: repository wins for *current facts*; higher layers win for
  *intent*.
- Prefer **HIGH/`V`** evidence over **MED/`A`** for current claims.
- A capability tagged `[hist:Lx]` means *its source is not in HEAD* — do **not** describe
  its runtime behavior as currently available.

## 3. Evidence verification protocol

Before asserting a fact as current:
1. Find the `EV` ID; read its `repo path`.
2. Confirm the path **exists in HEAD** (`git ls-files` / filesystem) — not just as `.pyc`.
3. If the file changed after the `EV` verification date, **re-verify** (the `EV` is stale).
4. If you cannot confirm, downgrade the claim to "per audit/history (unverified in HEAD)".

```
verify(EV):
  path = EV.repo_path
  if not exists_in_HEAD(path):            -> CLAIM = "absent in HEAD (lineage-B?)"  # EV-033 pattern
  elif mtime(path) > EV.date:             -> RE-VERIFY before use                    # stale
  elif EV.conf == HIGH and EV.basis == V: -> trust as current
  else:                                   -> trust with stated confidence
```

## 4. Confidence scoring (what to tell the user)

| Situation | Report as |
|---|---|
| HIGH/`V`, path in HEAD, fresh | "confirmed" |
| MED/`A`, path in HEAD, not re-checked | "likely (audit-sourced); re-verify" |
| path `.pyc`-only / absent in HEAD | "not present in current checkout (lineage-B)" |
| no citation found | "unverified — needs investigation" |

## 5. Conflict resolution

Follow `TRACEABILITY_STANDARD.md` §5: live `V` beats `A`; HEAD beats unmerged lineage for
current facts; higher authority beats lower for intent; ties → most recently verified, and
**log the resolution** (note which evidence you preferred and why).

## 6. Stale-evidence detection (the lineage hazard)

This repo's defining trap (EV-032/033/034, DD-009): the audited "production-ready" spine
is **`.pyc`-only in HEAD**. Rules:
- Treat any `EV` with basis `A` about `integrations/learning/**`, `integrations/highlight/**`,
  `integrations/shortgen/**`, `integrations/mcp/**`, or `render_to_memory` as **stale-risk**
  until re-confirmed against HEAD source.
- A `.pyc` without a sibling `.py` is **not** evidence of a present capability — it is
  evidence of a *missing* one (flag it).
- The `video-use` engine, `skills/**`, `memory/*.json|*.md`, and `timeline_to_edl.py` are
  the trustworthy present surface.

## 7. Exploration etiquette

- Cite IDs in answers (`TRACEABILITY_STANDARD.md`). No undocumented claims.
- When you discover a new repository fact, propose a new `EV` (append-only) rather than
  asserting it loosely.
- Respect the offline/local-first constraint (DD-006): do not assume network/paid-API
  availability when reasoning about the core path.
- Respect memory safety (DD-002): never propose writing `memory/` outside `safe_append`.
