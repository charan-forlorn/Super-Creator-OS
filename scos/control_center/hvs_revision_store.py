"""Append-only Stage 8B revision event ledger."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .hvs_local_delivery_service import _runtime_root
from .hvs_revision_models import RevisionAuditEvent
def revision_audit_path(repo_root: Path) -> Path: return _runtime_root(Path(repo_root)) / "hvs_revision_audit.jsonl"
def read_revision_events(*, audit_log_path: Any) -> tuple[RevisionAuditEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path): raise ValueError("unsafe revision store path")
    if not path.is_file(): return ()
    seen=set(); result=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: event=RevisionAuditEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc: raise ValueError(f"malformed revision event at line {n}") from exc
        if event.event_id in seen: raise ValueError("conflicting duplicate revision event id")
        seen.add(event.event_id); result.append(event)
    return tuple(result)
def append_revision_event(*, audit_log_path: Any, event: RevisionAuditEvent) -> RevisionAuditEvent:
    existing=read_revision_events(audit_log_path=audit_log_path)
    for seen in existing:
        if seen.event_id == event.event_id:
            if seen.to_dict()==event.to_dict(): return seen
            raise ValueError("conflicting duplicate revision event id")
    path=Path(audit_log_path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as f: f.write(json.dumps(event.to_dict(),sort_keys=True,separators=(",",":"))+"\n")
    return event
