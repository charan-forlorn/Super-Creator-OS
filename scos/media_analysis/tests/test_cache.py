from pathlib import Path
from scos.media_analysis.cache import file_sha256,analysis_key,load,store

def test_analysis_cache_roundtrip(tmp_path: Path):
    src=tmp_path/"a.txt"; src.write_text("hello",encoding="utf-8")
    key=analysis_key(src,{"silence_db":-45})
    assert len(file_sha256(src))==64
    p=store(tmp_path/"cache",key,{"ok":True})
    assert p.is_file()
    assert load(tmp_path/"cache",key)=={"ok":True}
    src.write_text("changed",encoding="utf-8")
    assert analysis_key(src,{"silence_db":-45})!=key
