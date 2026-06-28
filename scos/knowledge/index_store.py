"""SCOS Stage 3.5 — Knowledge Index persistence (IndexStore).

The ONLY module in scos/knowledge/ that imports json or touches index.json
directly. knowledge_index.py and query.py depend on this abstraction only
(save/load of a KnowledgeIndex object) — never on JSON specifics — so a future
SQLite/DuckDB-backed IndexStore is a drop-in replacement with no change to the
builder or query layer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_models import KnowledgeIndex  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _REPO_ROOT / "scos" / "work" / "knowledge" / "index.json"


class IndexStore:
    """Atomic JSON-backed persistence for one KnowledgeIndex."""

    def __init__(self, path: Path | str = _DEFAULT_PATH) -> None:
        self.path = Path(path)

    def save(self, index: KnowledgeIndex) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(index.to_dict(), sort_keys=True, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)  # atomic on same filesystem

    def load(self) -> KnowledgeIndex:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return KnowledgeIndex.from_dict(data)

    def exists(self) -> bool:
        return self.path.exists()
