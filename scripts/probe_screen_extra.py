from pathlib import Path
import json, subprocess, numpy as np
p=Path(r"C:/Users/chara/OneDrive/Videos/Screen Recordings/Screen Recording 2026-09-04 152518.mp4")
o=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height,duration,r_frame_rate","-of","json",str(p)],capture_output=True,text=True,check=True)
probe=json.loads(o.stdout)["streams"][0]
dur=float(probe["duration"]); w=160; h=max(2,round(w*int(probe["height"])/int(probe["width"])/2)*2)
raw=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-t",str(dur),"-i",str(p),"-vf",f"scale={w}:{h},format=gray,fps=5","-f","rawvideo","-pix_fmt","gray","pipe:1"],capture_output=True,check=True).stdout
fb=w*h; frames=np.frombuffer(raw[:len(raw)//fb*fb],dtype=np.uint8).reshape((-1,h,w)).astype(np.float32)/255
dif=np.mean(np.abs(frames[1:]-frames[:-1]),axis=(1,2)); scores=[]
for i in range(max(1,len(dif)-4)): scores.append((float(np.mean(dif[i:i+5])),i/5))
scores.sort(reverse=True); chosen=[]
for s,t in scores:
    if all(abs(t-x[1])>=2 for x in chosen): chosen.append((s,t))
    if len(chosen)>=5: break
data={"probe":probe,"top_windows":[{"score":s,"start":t,"end":min(dur,t+1)} for s,t in chosen]}
Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/screen_recording_extra_motion.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(data,ensure_ascii=False,indent=2))
