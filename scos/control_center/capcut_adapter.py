from __future__ import annotations
import json,os,shutil,subprocess
from pathlib import Path
from typing import Any

class CapCutAdapterError(RuntimeError): pass

def _command(args:list[str])->list[str]:
    script=Path(os.environ.get("SCOS_CAPCUT_JS",Path.home()/"AppData/Roaming/npm/node_modules/capcut-cli/dist/index.js")).resolve()
    if not script.is_file():
        raise CapCutAdapterError(f"CapCut CLI entry not found: {script}")
    node=os.environ.get("SCOS_NODE_BIN") or shutil.which("node")
    if not node:
        raise CapCutAdapterError("Node.js executable not found")
    return [node,str(script),*args]

def _run(args:list[str],timeout:int=120)->dict[str,Any]:
    p=subprocess.run(_command(args),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,check=False)
    text=(p.stdout or "").strip()
    if p.returncode!=0: raise CapCutAdapterError((p.stderr or text)[-3000:])
    try:
        value=json.loads(text)
        return value if isinstance(value,dict) else {"result":value}
    except json.JSONDecodeError:
        return {"result":text}

def create_draft(name:str,video:str|Path,srt:str|Path,width:int,height:int)->dict[str,Any]:
    return _run(["quickstart",name,"--video",str(Path(video).resolve()),"--srt",str(Path(srt).resolve()),"--width",str(width),"--height",str(height)])

def lint(project:str|Path)->dict[str,Any]:
    return _run(["lint",str(Path(project).resolve())])

def text_segments(project:str|Path)->dict[str,Any]:
    return _run(["segments",str(Path(project).resolve()),"--track","text"])

def repair_fast_caption(project:str|Path,segment_id:str,duration_ms:int=450)->dict[str,Any]:
    return _run(["trim",str(Path(project).resolve()),segment_id,"137ms",f"{duration_ms}ms"])

def verified_lint(project:str|Path)->dict[str,Any]:
    return lint(project)
