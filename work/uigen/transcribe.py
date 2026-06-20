"""transcribe.py — word-level ASR for lyric timing using openai-whisper (OpenAI CDN)."""
import json, time
from pathlib import Path
import whisper

SONG = r"C:/Users/chara/super-creator-os/input/song/blackbear - hot girl bummer [Low Budget Video].m4a"
OUT = Path(__file__).parent / "lyrics_words.json"

t0 = time.time()
model = whisper.load_model("small")
print("model loaded %.1fs" % (time.time() - t0))
res = model.transcribe(SONG, language="en", word_timestamps=True, verbose=False)
segs = []
for s in res["segments"]:
    words = [{"w": w["word"], "s": round(w["start"], 2), "e": round(w["end"], 2)} for w in s.get("words", [])]
    segs.append({"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip(), "words": words})
    print(f"[{s['start']:6.2f}-{s['end']:6.2f}] {s['text'].strip()}")
OUT.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwrote", OUT, "segments:", len(segs), "(%.1fs total)" % (time.time() - t0))
