# AI Query Protocol

> **Status:** ACTIVE (Phase 2.9.3). The step pipeline **every** AI agent runs to answer a
> question about Super Creator OS. Pairs with `KNOWLEDGE_RETRIEVAL.md` (where to look) — this
> doc is *how to process*. Citation rules: `TRACEABILITY_STANDARD.md`.

---

## 1. The pipeline

```
Question
  → 1. Question Classification
  → 2. Knowledge Search        (KNOWLEDGE_RETRIEVAL order: Authority→EV→DD→CAP→Repo→Hist→Ext)
  → 3. Evidence Validation
  → 4. Decision Lookup
  → 5. Capability Lookup
  → 6. Repository Verification  (verify only; never primary)
  → 7. Answer Construction
  → 8. Confidence Reporting
Answer (+ citations + confidence)
```

## 2. Step detail

| Step | Action | Output |
|---|---|---|
| 1 Question Classification | Tag the question: *current-fact* / *intent* / *capability* / *how-to* / *historical*. Determines the authoritative source (`AUTHORITY_MODEL.md` §3). | question type |
| 2 Knowledge Search | Walk the `KNOWLEDGE_RETRIEVAL.md` order; stop when answered. | candidate `EV`/`DD`/`CAP` |
| 3 Evidence Validation | For each `EV`: confirm it exists; check confidence/basis; if path-bearing and current-fact, mark for repo verify. | validated EV set |
| 4 Decision Lookup | If the question is "why/should", attach the governing `DD` (and the higher-authority doc for intent). | DD set |
| 5 Capability Lookup | If about a feature, resolve the `CAP`: owner, current/target maturity, `[hist:…]`. | CAP record |
| 6 Repository Verification | Only for current-fact claims: confirm the cited path exists in HEAD as `.py` (not `.pyc`-only). | verified / "absent in HEAD" |
| 7 Answer Construction | Compose the answer **from EKB facts**, ordered intent-then-fact; include `EV`/`DD`/`CAP` citations inline. | drafted answer |
| 8 Confidence Reporting | Attach confidence = weakest evidence used (`KNOWLEDGE_RETRIEVAL.md` §3); note staleness/lineage caveats. | final answer |

## 3. Decision rules embedded in the pipeline

- **Classify before searching.** An *intent* question is answered by the higher document
  (Vision/Constitution/Spec), not by implementation facts (anti-pattern: deriving a
  principle from code — forbidden, `AUTHORITY_MODEL.md` §3).
- **Never let step 6 become step 2.** Repository verification is confirmation, not
  discovery. If you find yourself reading source to *learn* a fact, capture it as a new
  `EV` first.
- **Fail loud, not silent.** Unresolved `EV`/`DD`/`CAP`/term/path → stop and report
  "Unverified / Not enough evidence" (`TRACEABILITY_STANDARD.md`).

## 4. Output contract

Every answer returns: **(a)** the answer, **(b)** citations (`EV`/`DD`/`CAP` + paths),
**(c)** confidence label, **(d)** any caveat (stale / lineage-B / intent-vs-fact). Answers
without (b) and (c) are non-compliant.

## 5. Minimal pseudo-procedure

```
answer(q):
  t = classify(q)
  src = authority_for(t)                    # AUTHORITY_MODEL
  hits = search(q, order=RETRIEVAL_ORDER)   # KNOWLEDGE_RETRIEVAL
  ev = validate(hits.EV); dd = lookup(hits.DD); cap = lookup(hits.CAP)
  if t == current_fact: verify_in_HEAD(ev.paths)   # step 6, confirm only
  if unresolved(ev, dd, cap): return "Not enough evidence", cite gaps
  return compose(src, ev, dd, cap), cites(ev,dd,cap), confidence(min(ev))
```
