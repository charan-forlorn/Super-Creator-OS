"""build_combo.py — Canva cover intro -> beat-synced UI edit, scored to the real
Higgsfield beat. Demonstrates the MCP-sourced assets inside the existing pipeline.
Vertical 1080x1920, 30fps, ~20s. Additive; outputs to output/.
"""
import numpy as np, subprocess, math, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- Central media-binary resolver ------------------------------------------
# Keep build_combo.py runnable as a standalone script and importable
# under pytest while routing ffmpeg through the shared, hermetic
# resolver. Repo root is added to sys.path so the in-package
# resolver is importable without a hardcoded path. Resolution is
# lazy (module import) and fails closed with an actionable error.
import sys  # noqa: E402
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from scos.media_binaries import resolve_ffmpeg  # noqa: E402

FFMPEG = resolve_ffmpeg()

HERE=Path(__file__).parent
W,H,FPS=1080,1920,30
CARD_CY=820
COVER=HERE.parent/"assets_mcp"/"canva_cover_1080x1920.png"
BEAT=HERE.parent/"assets_mcp"/"higgsfield_beat_20s.m4a"
PINK=(255,45,155); RED=(255,59,48); CYAN=(0,229,255); LIME=(200,255,0); VIOLET=(139,92,246); GREEN=(52,199,89); BLUE=(10,132,255)

FD="C:/Windows/Fonts/"; _fc={}
def F(n,s):
    k=(n,s)
    if k not in _fc:_fc[k]=ImageFont.truetype(FD+n,s)
    return _fc[k]
def bold(s):return F("arialbd.ttf",s)
def reg(s):return F("arial.ttf",s)
def emo(s):return F("seguiemj.ttf",s)
def is_emoji(ch):
    o=ord(ch);return (0x1F000<=o<=0x1FAFF)or(0x2600<=o<=0x27BF)or(0x2B00<=o<=0x2BFF)or(0x1F1E6<=o<=0x1F1FF)or o in(0x2934,0x2935)
def rsize(d,t,f,ef):
    w=0;h=0
    for ch in t:
        if ch=='️':continue
        ff=ef if is_emoji(ch) else f;bb=d.textbbox((0,0),ch,font=ff);w+=bb[2]-bb[0];h=max(h,bb[3]-bb[1])
    return w,h
def rich(d,xy,t,f,ef,fill,center=False):
    x,y=xy
    if center:w,_=rsize(d,t,f,ef);x-=w/2
    for ch in t:
        if ch=='️':continue
        if is_emoji(ch):
            try:d.text((x,y),ch,font=ef,embedded_color=True);bb=d.textbbox((0,0),ch,font=ef);x+=bb[2]-bb[0]
            except Exception:bb=d.textbbox((0,0),ch,font=f);x+=bb[2]-bb[0]
        else:d.text((x,y),ch,font=f,fill=fill);bb=d.textbbox((0,0),ch,font=f);x+=bb[2]-bb[0]
def canvas(h,w=920):return Image.new("RGBA",(w,h),(0,0,0,0))
def rr(d,box,r,fill=None,outline=None,width=2):d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)
def glass(im,box,r=40,fill=(28,28,30,240),border=(255,255,255,30)):
    d=ImageDraw.Draw(im);rr(d,box,r,fill=fill);rr(d,box,r,outline=border,width=2)
def circ(im,cx,cy,rad,color,glyph=None,gs=None):
    d=ImageDraw.Draw(im);d.ellipse([cx-rad,cy-rad,cx+rad,cy+rad],fill=color+(255,))
    if glyph:rich(d,(cx,cy-rad*0.72),glyph,emo(gs or int(rad)),emo(gs or int(rad)),(255,255,255,255),center=True)

# ---- cover (Canva) ----
cover=Image.open(COVER).convert("RGBA").resize((W,H))
album=Image.open(COVER).convert("RGBA").crop((300,470,780,950)).resize((300,300))  # pink marble swatch for album art

def b_notif(_,acc):
    im=canvas(220);glass(im,[40,20,880,200],r=34)
    d=ImageDraw.Draw(im);circ(im,130,110,52,acc,"🎧",60)
    d.text((215,55),"Now Playing • now",font=bold(34),fill=(255,255,255,255))
    rich(d,(215,108),"Hot Girl Vibes 🔥",reg(38),emo(38),(210,210,215,255))
    return im
def b_music(_,acc):
    im=canvas(640);glass(im,[40,20,880,620],r=46,fill=(18,18,20,246))
    im.paste(album,(310,60),album)
    d=ImageDraw.Draw(im)
    d.text((460,400),"Hot Girl Vibes",font=bold(50),fill=(255,255,255,255),anchor="mm")
    d.text((460,452),"Super Creator OS • Higgsfield beat",font=reg(30),fill=(180,180,185,255),anchor="mm")
    rr(d,[120,520,760,548],14,fill=(60,60,64,255));rr(d,[120,520,420,548],14,fill=acc+(255,))
    for cx,g in[(330,"⏮"),(460,"⏸"),(590,"⏭")]:rich(d,(cx,585),g,emo(46),emo(46),(255,255,255,255),center=True)
    return im
def b_react(_,acc):
    im=canvas(520);d=ImageDraw.Draw(im)
    circ(im,460,180,150,acc,"❤️",170)
    d.text((460,380),"12.4k",font=bold(80),fill=(255,255,255,255),anchor="mm")
    d.text((460,460),"likes & climbing",font=reg(36),fill=(200,200,205,255),anchor="mm")
    return im
def b_poll(_,acc):
    im=canvas(440);glass(im,[40,30,880,420],r=44,fill=(18,18,20,245));d=ImageDraw.Draw(im)
    d.text((460,95),"this edit??",font=bold(54),fill=(255,255,255,255),anchor="mm")
    rr(d,[90,180,830,270],26,fill=(50,50,54,255));rr(d,[90,180,90+int(740*0.88),270],26,fill=acc+(255,))
    rich(d,(120,196),"🔥 fire",bold(44),emo(44),(0,0,0,255));d.text((800,196),"88%",font=bold(42),fill=(0,0,0,255),anchor="ra")
    rr(d,[90,300,830,390],26,fill=(50,50,54,255));rr(d,[90,300,90+int(740*0.12),390],26,fill=(90,90,95,255))
    rich(d,(120,316),"💯 mid",bold(44),emo(44),(220,220,225,255));d.text((800,316),"12%",font=bold(42),fill=(180,180,185,255),anchor="ra")
    return im
def b_grid(_,acc):
    im=canvas(560);apps=[((52,199,89),"💬"),(acc,"🎵"),((10,132,255),"📷"),((255,138,0),"🔥"),((175,82,222),"🎮"),((255,204,0),"⭐"),((255,59,48),"❤"),((90,200,250),"☁"),((52,199,89),"✨")]
    d=ImageDraw.Draw(im);s=240;gap=30
    for i,(col,g) in enumerate(apps):
        x=40+(i%3)*(s+gap);y=20+(i//3)*(s-40+gap);rr(d,[x,y,x+s,y+s-40],46,fill=col+(255,))
        rich(d,(x+s/2,y+(s-40)/2-55),g,emo(110),emo(110),(255,255,255,255),center=True)
    return im
def b_comments(_,acc):
    im=canvas(520);d=ImageDraw.Draw(im)
    rows=[("riarix","🔥🔥🔥 insane edit"),("user_x","on repeat fr"),("editzz","who made this?? 👀")]
    y=20
    for nm,msg in rows:
        glass(im,[40,y,880,y+150],r=30);circ(im,130,y+75,46,acc)
        d.text((215,y+38),nm,font=bold(34),fill=(255,255,255,255));rich(d,(215,y+88),msg,reg(36),emo(36),(210,210,215,255));y+=170
    return im
def b_share(_,acc):
    im=canvas(420);d=ImageDraw.Draw(im)
    rich(d,(460,20),"that's a wrap ✨",bold(60),emo(60),(255,255,255,255),center=True)
    glass(im,[150,150,770,270],r=60,fill=acc+(255,),border=(0,0,0,0))
    rich(d,(460,176),"Share this story 📲",bold(46),emo(46),(0,0,0,255),center=True)
    d.text((460,330),"made with Super Creator OS",font=reg(34),fill=(170,170,175,255),anchor="mm")
    return im

# (start, kind, builder, caption, accent) ; kind 'cover' handled specially
SC=[
 (0.0,"cover",None,"new drop 🔥",PINK),
 (3.0,"card",b_notif,"now playing 🎧",PINK),
 (5.4,"card",b_music,"the Higgsfield beat 🎵",PINK),
 (8.0,"card",b_react,"chat went crazy ❤️",RED),
 (10.2,"card",b_poll,"you already know 🔥",CYAN),
 (12.6,"card",b_grid,"all the vibes ✨",VIOLET),
 (15.0,"card",b_comments,"comments don't lie 👀",LIME),
 (17.4,"card",b_share,"share it 📲",PINK),
]
TEND=20.0
starts=[s[0] for s in SC]

# ---- audio envelope from the real beat ----
wavp=HERE/"_beat.wav"
subprocess.run([FFMPEG,"-hide_banner","-y","-i",str(BEAT),"-ar","44100","-ac","1",str(wavp)],stderr=subprocess.DEVNULL)
with wave.open(str(wavp),'rb') as w:
    sr=w.getframerate();raw=w.readframes(w.getnframes())
a=np.frombuffer(raw,np.int16).astype(np.float32)/32768.0
NF=int(TEND*FPS);env=np.zeros(NF);win=int(sr/FPS)
for f in range(NF):
    i=int(f/FPS*sr);seg=a[i:i+win];env[f]=math.sqrt(float(np.mean(seg**2))+1e-9) if len(seg) else 0
env=env/(np.percentile(env,95)+1e-9);env=np.clip(env,0,1.4)

G=560;gy,gx=np.mgrid[0:G,0:G];gd=np.sqrt((gx-G/2)**2+(gy-G/2)**2)/(G/2);GLOW=(np.clip(1-gd,0,1)**2*255).astype(np.uint8)
bgv=np.zeros((H,W,3),np.float32);yy,xx=np.mgrid[0:H,0:W];dist=np.sqrt((xx-W/2)**2+(yy-H*0.42)**2)/(0.8*math.hypot(W/2,H/2))
BG=Image.fromarray((np.clip(1-dist,0,1)[...,None]*np.array([20,8,16])).astype(np.uint8),"RGB").convert("RGBA")

def status(d):
    d.text((60,46),"9:41",font=bold(40),fill=(255,255,255,255));bx=W-70
    d.rounded_rectangle([bx-60,52,bx,84],6,outline=(255,255,255,200),width=3);d.rounded_rectangle([bx-56,56,bx-20,80],3,fill=(255,255,255,230));d.rectangle([bx+2,60,bx+8,76],fill=(255,255,255,200))
    for i,hh in enumerate([10,16,22,28]):d.rounded_rectangle([bx-150+i*16,84-hh,bx-150+i*16+10,84],2,fill=(255,255,255,220))
def cap_img(t,acc):
    tmp=Image.new("RGBA",(W,140),(0,0,0,0));d=ImageDraw.Draw(tmp);w,_=rsize(d,t,bold(58),emo(58))
    rich(d,(W/2,28),t,bold(58),emo(58),(255,255,255,255),center=True);rr(d,[W/2-w/2-8,104,W/2-w/2+min(w,140),116],6,fill=acc+(255,));return tmp
caps=[cap_img(c,a) for (_,_,_,c,a) in SC]
cards={}
for i,(st,kind,fn,cap,acc) in enumerate(SC):
    if kind=="card":cards[i]=fn(None,acc)
def eob(x):c1=1.70158;c3=c1+1;return 1+c3*((x-1)**3)+c1*((x-1)**2)
def sm(x):return x*x*(3-2*x)
def scene_at(tt):
    si=0
    for i,s in enumerate(starts):
        if tt>=s:si=i
    return si

out=Path("C:/Users/chara/super-creator-os/output/COMBO_canva_higgsfield_uiedit.mp4")
cmd=[FFMPEG,"-y","-f","rawvideo","-pix_fmt","rgb24","-s","%dx%d"%(W,H),"-r",str(FPS),"-i","-","-i",str(BEAT),
     "-c:v","libx264","-pix_fmt","yuv420p","-profile:v","high","-crf","19","-preset","medium","-c:a","aac","-b:a","192k","-shortest",str(out)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
print("rendering %d frames..."%NF)
for f in range(NF):
    tt=f/FPS;si=scene_at(tt);st,kind,fn,cap,acc=SC[si];nxt=starts[si+1] if si+1<len(starts) else TEND
    dur=nxt-st;local=tt-st;e=env[f]
    if kind=="cover":
        # cover with slow zoom + flash-out at end
        z=1.0+0.10*(local/dur)
        cw,ch=int(W*z),int(H*z);ci=cover.resize((cw,ch))
        frame=Image.new("RGBA",(W,H),(0,0,0,255));frame.alpha_composite(ci,(int((W-cw)/2),int((H-ch)/2)))
        d=ImageDraw.Draw(frame)
        # tap ring near PLAY (~ y 1300) pulsing
        if local>1.2:
            rp=int(40+ (math.sin(tt*6)*0.5+0.5)*40);d.ellipse([W/2-rp,1300-rp,W/2+rp,1300+rp],outline=(255,255,255,180),width=5)
        if local>dur-0.3:
            fl=int(sm((local-(dur-0.3))/0.3)*255);ov=Image.new("RGBA",(W,H),(255,255,255,fl));frame.alpha_composite(ov)
        proc.stdin.write(frame.convert("RGB").tobytes())
        if f%60==0:print("  %d/%d"%(f,NF))
        continue
    card=cards[si];frame=BG.copy()
    gsz=int(560+e*220);gi=Image.new("RGBA",(gsz,gsz),acc+(0,));al=Image.fromarray(GLOW,"L").resize((gsz,gsz)).point(lambda p:int(p*(0.10+0.22*e)));gi.putalpha(al)
    frame.alpha_composite(gi,(int(W/2-gsz/2),int(CARD_CY-gsz/2)))
    cw,ch=card.size;tin=0.18;tout=0.12
    if local<tin:p=local/tin;ee=eob(min(p,1));scale=0.82+0.18*ee;alpha=sm(min(p,1));dy=(1-sm(min(p,1)))*50
    elif local>dur-tout:p=(local-(dur-tout))/tout;scale=1.0-0.04*p;alpha=1-sm(min(p,1));dy=-sm(min(p,1))*24
    else:scale=1.0+0.03*e;alpha=1.0;dy=math.sin(tt*2)*4
    nw,nh=max(1,int(cw*scale)),max(1,int(ch*scale));cim=card.resize((nw,nh))
    if alpha<1:cim.putalpha(cim.split()[3].point(lambda p:int(p*alpha)))
    frame.alpha_composite(cim,(int(W/2-nw/2),int(CARD_CY-nh/2+dy)))
    capim=caps[si]
    ca=sm(local/0.12) if local<0.12 else (1-sm(min((local-(dur-tout))/tout,1)) if local>dur-tout else 1.0)
    if ca>0:
        ci=capim if ca>=1 else capim.copy()
        if ca<1:ci.putalpha(ci.split()[3].point(lambda p:int(p*ca)))
        frame.alpha_composite(ci,(0,1500))
    d=ImageDraw.Draw(frame)
    pw=int((tt/TEND)*(W-120));d.rounded_rectangle([60,70,W-60,78],4,fill=(255,255,255,40));d.rounded_rectangle([60,70,60+pw,78],4,fill=acc+(255,))
    d.text((W/2,1850),"@phone.goes.brrr",font=reg(32),fill=(150,150,155,255),anchor="mm")
    proc.stdin.write(frame.convert("RGB").tobytes())
    if f%60==0:print("  %d/%d"%(f,NF))
proc.stdin.close();proc.wait()
try:wavp.unlink()
except Exception:pass
print("DONE ->",out)
