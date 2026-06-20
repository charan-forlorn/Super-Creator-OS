"""gen_broll.py — offline procedural B-roll (no AI credits, no network).
Animated plasma gradient + drifting bokeh, vertical 1080x1920. A free stand-in for
AI b-roll: use as an intro/overlay background under UI cards or text.
Output: work/assets_mcp/broll_plasma_8s.mp4  (8s, 30fps, no audio).
"""
import numpy as np, subprocess, math
from pathlib import Path

W,H,FPS,DUR=1080,1920,30,8.0
NF=int(DUR*FPS)
# low-res plasma then upscale (cheap + smooth)
w,h=270,480
yy,xx=np.mgrid[0:h,0:w].astype(np.float32)
xn,yn=xx/w,yy/h
# palette: dark purple -> violet -> hot pink -> magenta (no muddy mid-tones)
_POS=np.array([0.0,0.40,0.72,1.0])
_STOPS=np.array([[18,5,38],[95,20,120],[255,45,155],[185,70,255]],dtype=np.float32)/255.0
def palette(v):
    t=np.clip(v*0.5+0.5,0,1); tf=t.ravel(); sh=t.shape
    r=np.interp(tf,_POS,_STOPS[:,0]).reshape(sh)
    g=np.interp(tf,_POS,_STOPS[:,1]).reshape(sh)
    b=np.interp(tf,_POS,_STOPS[:,2]).reshape(sh)
    return r,g,b

# drifting bokeh
rng=np.random.RandomState(7)
NB=14
bx=rng.uniform(0,1,NB); by=rng.uniform(0,1,NB); br=rng.uniform(0.04,0.12,NB)
bsx=rng.uniform(-0.03,0.03,NB); bsy=rng.uniform(-0.05,0.05,NB)

out=Path("C:/Users/chara/super-creator-os/work/assets_mcp/broll_plasma_8s.mp4")
cmd=["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
     "-c:v","libx264","-pix_fmt","yuv420p","-crf","20","-preset","medium",str(out)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
print("rendering broll %d frames"%NF)
for f in range(NF):
    t=f/FPS
    v=(np.sin((xn*3.0)+t*0.8)+np.sin((yn*4.0)-t*0.6)+np.sin((xn+yn)*3.5+t)+np.sin(np.hypot(xn-0.5,yn-0.5)*8-t*1.4))
    v=v/4.0
    r,g,b=palette(v)
    img=np.stack([r,g,b],-1)
    # bokeh additive
    for i in range(NB):
        cx=(bx[i]+bsx[i]*t)%1.0; cy=(by[i]+bsy[i]*t)%1.0
        d2=((xn-cx)**2+(yn-cy)**2)/(br[i]**2)
        glow=np.exp(-d2)*0.35
        img[...,0]+=glow; img[...,1]+=glow*0.15; img[...,2]+=glow*0.7  # pink-tinted bokeh
    img=np.clip(img*255,0,255).astype(np.uint8)
    big=np.array(__import__("PIL.Image",fromlist=["Image"]).fromarray(img,"RGB").resize((W,H)))
    # subtle vignette
    proc.stdin.write(big.tobytes())
    if f%60==0:print("  %d/%d"%(f,NF))
proc.stdin.close();proc.wait()
print("DONE ->",out)
