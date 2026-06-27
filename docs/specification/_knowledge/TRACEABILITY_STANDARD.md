# Traceability Standard

> **Status:** ACTIVE (Phase 2.8). The binding rule for **every** future document in this
> knowledge system (Phases 3–13 and beyond). Goal: **no undocumented claims.** Every
> assertion is traceable to repository evidence and back.

---

## 1. The rule

> Any factual claim about the system — what it does, how it is built, what state it is in —
> **must cite** at least one of: an Evidence ID (`EV-xxx`), a Decision ID (`DD-xxx`), a
> Capability ID (`CAP-xxx`), or a direct repository path. Claims about *intent* (what the
> system *should* do) must cite the higher-authority document that sets that intent
> (see `AUTHORITY_MODEL.md`).

A statement with no citation is treated as **unverified** and may not be relied upon by an
AI agent or promoted to RATIFIED status.

## 2. ID rules

- **Immutable & append-only.** Once minted, an `EV`/`DD`/`CAP` ID is never reused,
  renumbered, or deleted. Zero-padded to 3 digits (`EV-007`).
- **Supersession, not deletion.** A wrong or outdated item is marked
  `SUPERSEDED-BY: EV-xxx` (and the new item carries `SUPERSEDES: EV-yyy`). The original
  row stays for history.
- **Single home per ID type:** `EV` → `EVIDENCE_REGISTER.md`; `DD` → `DECISION_REGISTER.md`;
  `CAP` → `CAPABILITY_INVENTORY.md` (spine) / `CAPABILITY_REGISTRY.md` (governance).
- **Terms** resolve to exactly one definition in `GLOSSARY.md` (no second glossary).

## 3. Citation forms

| Claim type | Required citation | Example |
|---|---|---|
| Current fact | `EV-xxx` (+ repo path if not in the EV row) | "Memory has 2 records (EV-015)." |
| Design/governance choice | `DD-xxx` | "Writes go through one path (DD-002)." |
| Capability statement | `CAP-xxx` | "Highlight detection (CAP-003) is L2." |
| Intent / requirement | higher-doc ref | "Per Constitution §5.1, integrity beats speed." |
| Maturity claim | `CAP-xxx` + `MATURITY_MODEL.md` level | "CAP-014 is L2 as-of-HEAD." |

## 4. Confidence & freshness

- Every `EV` carries **confidence** (HIGH/MED/LOW) and **verification basis** (`V` live /
  `A` audit) with a date. Claims inherit the confidence of their weakest cited `EV`.
- An `EV` older than its source's last change is **stale** and must be re-verified before
  reuse (see `REPOSITORY_INTELLIGENCE.md` §stale-evidence). MED/`A` evidence about
  lineage-B modules is inherently stale-risk and must be re-checked against HEAD.

## 5. Conflict resolution (which citation wins)

1. A live repository check (`V`) beats an audit citation (`A`) for *current* facts.
2. `EV` about HEAD beats `EV` about an unmerged lineage for *current* facts.
3. For *intent*, higher authority layer wins (`AUTHORITY_MODEL.md` §3).
4. Ties resolve to the most recently verified item; log the resolution.

## 6. What this forbids

- ❌ Asserting a capability is "production ready" without L5 evidence (`MATURITY_MODEL.md`).
- ❌ Citing the Evidence Ledger prose instead of an `EV` ID (use the ID).
- ❌ Introducing a term not in `GLOSSARY.md`, or a second definition of an existing term.
- ❌ Deriving a constitutional principle from an implementation detail (`AUTHORITY_MODEL.md` §3).
- ❌ Trusting a lineage-B module's behavior as *current* without re-verifying source in HEAD.

## 7. Compliance check (run before ratifying any doc)

`grep -oE '(EV|DD|CAP)-[0-9]{3}'` the document → every ID must resolve to an existing row
in its register; every major claim paragraph must contain ≥1 citation; every term must
exist in the glossary. Coverage is measured in `KNOWLEDGE_QUALITY_METRICS.md`.
