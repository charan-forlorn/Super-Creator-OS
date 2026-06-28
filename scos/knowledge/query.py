"""SCOS Stage 3.5 — Knowledge Index query layer.

Public read-only search API over an already-built/loaded KnowledgeIndex. Every
find_*/timeline/statistics function operates purely on the in-memory object —
none of them touch index.json or any source artifact directly. Persistence is
exclusively IndexStore's job (see index_store.py); build()/load() below are the
only two functions that talk to it.

All queries are deterministic: identical KnowledgeIndex in -> identical result
out, every time.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from index_store import IndexStore  # noqa: E402
from knowledge_models import (  # noqa: E402
    KnowledgeIndex, SOURCE_LEARNING_AUDIT,
    DECISION_APPLY, DECISION_CLAMP, DECISION_REJECT, DECISION_FAIL, DECISION_ROLLBACK,
)

_APPLIED_DECISIONS = (DECISION_APPLY, DECISION_CLAMP)
_FAILED_DECISIONS = (DECISION_REJECT, DECISION_FAIL)


def build(indexer: "LearningKnowledgeIndex | None" = None,
          store: "IndexStore | None" = None, now_fn=None) -> KnowledgeIndex:
    """Build a fresh KnowledgeIndex from the source artifacts and persist it."""
    indexer = indexer or LearningKnowledgeIndex()
    store = store or IndexStore()
    index = indexer.build() if now_fn is None else indexer.build(now_fn=now_fn)
    store.save(index)
    return index


def load(store: "IndexStore | None" = None) -> KnowledgeIndex:
    """Load the most recently persisted KnowledgeIndex. Delegates to IndexStore —
    never opens index.json itself."""
    store = store or IndexStore()
    return store.load()


def find_event(index: KnowledgeIndex, run_id: str) -> list:
    return [e for e in index.events if e.run_id == run_id]


def find_style(index: KnowledgeIndex, style_id: str):
    return index.timeline.get(style_id)


def find_replay(index: KnowledgeIndex, replay_id: str) -> list:
    return [e for e in index.events if e.replay_id == replay_id]


def find_rollbacks(index: KnowledgeIndex) -> list:
    return [e for e in index.events if e.decision == DECISION_ROLLBACK]


def find_best_style(index: KnowledgeIndex):
    """Highest quality_score among APPLY/CLAMP learning_audit-sourced events
    (the canonical decision record — style_history events inherit the same
    decision but are not double-counted here). Ties broken by style_id
    ascending for determinism."""
    best = None
    for sid, tl in index.timeline.items():
        for e in tl.events:
            if (e.source == SOURCE_LEARNING_AUDIT
                    and e.decision in _APPLIED_DECISIONS
                    and e.metrics.get("quality_score") is not None):
                candidate = (e.metrics["quality_score"], sid, e)
                if best is None or candidate[0] > best[0] or (
                        candidate[0] == best[0] and candidate[1] < best[1]):
                    best = candidate
    return best[2] if best else None


def find_failed_learning(index: KnowledgeIndex) -> list:
    return [e for e in index.events if e.decision in _FAILED_DECISIONS]


def timeline(index: KnowledgeIndex, style_id: str):
    return index.timeline.get(style_id)


def statistics(index: KnowledgeIndex) -> dict:
    return index.statistics
