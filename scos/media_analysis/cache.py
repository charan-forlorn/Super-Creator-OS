from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from typing import Any

CACHE_SCHEMA=1

def file_sha256(path: str|Path)->str:
    h=hashlib.sha256()
    with open(Path(path).resolve(),"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def analysis_key(source: str|Path, config: dict[str,Any])->str:
    payload={"schema":CACHE_SCHEMA,"source_sha256":file_sha256(source),"config":config}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def load(root: str|Path,key: str)->dict[str,Any]|None:
    p=Path(root).resolve()/f"{key}.json"
    if not p.is_file(): return None
    try:
        data=json.loads(p.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):
        return None
    if data.get("schema")!=CACHE_SCHEMA or data.get("key")!=key:
        return None
    return data.get("evidence")

def store(root: str|Path,key: str,evidence: dict[str,Any])->Path:
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    target=root/f"{key}.json"; temp=target.with_suffix(f".tmp.{os.getpid()}.json")
    temp.write_text(json.dumps({"schema":CACHE_SCHEMA,"key":key,"evidence":evidence},ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temp,target)
    return target
