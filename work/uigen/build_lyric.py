"""build_lyric.py — "hot girl bummer" fake phone-UI LYRIC edit (Super Creator OS).
Each lyric line is rendered AS a believable iOS UI surface, beat-synced to the real
song via an amplitude envelope. Vertical 1080x1920, 30fps, ~51s.
"""
import numpy as np, subprocess, math, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).parent
W,H,FPS=1080,1920,30
CARD_CY=820
AUDIO=HERE/"audio_clip.wav"
PINK=(255,45,155); RED=(255,59,48); CYAN=(0,229,255); LIME=(200,255,0)
VIOLET=(139,92,246); ORANGE=(255,138,0); GREEN=(52,199,89); BLUE=(10,132,255); YELL=(255,204,0)

FD="C:/Windows/Fonts/"; _fc={}
def F(n,s):
    k=(n,s)
    if k not in _fc:_fc[k]=ImageFont.truetype(FD+n,s)
    return _fc[k]
def bold(s):return F("arialbd.ttf",s)
def reg(s):return F("arial.ttf",s)
def emo(s):return F("seguiemj.ttf",s)
def is_emoji(ch):
    o=ord(ch)
    return (0x1F000<=o<=0x1FAFF)or(0x2600<=o<=0x27BF)or(0x2B00<=o<=0x2BFF)or(0x1F1E6<=o<=0x1F1FF)or o in(0x2934,0x2935,0x2B05)
def rsize(d,t,f,ef):
    w=0;h=0
    for ch in t:
        if ch=='️':continue
        ff=ef if is_emoji(ch) else f; bb=d.textbbox((0,0),ch,font=ff); w+=bb[2]-bb[0]; h=max(h,bb[3]-bb[1])
    return w,h
def rich(d,xy,t,f,ef,fill,center=False):
    x,y=xy
    if center: w,_=rsize(d,t,f,ef); x-=w/2
    for ch in t:
        if ch=='️':continue
        if is_emoji(ch):
            try:
                d.text((x,y),ch,font=ef,embedded_color=True); bb=d.textbbox((0,0),ch,font=ef); x+=bb[2]-bb[0]
            except Exception:
                bb=d.textbbox((0,0),ch,font=f); x+=bb[2]-bb[0]
        else:
            d.text((x,y),ch,font=f,fill=fill); bb=d.textbbox((0,0),ch,font=f); x+=bb[2]-bb[0]
def canvas(h,w=920):return Image.new("RGBA",(w,h),(0,0,0,0))
def rr(d,box,r,fill=None,outline=None,width=2):d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)
def glass(im,box,r=40,fill=(28,28,30,240),border=(255,255,255,30)):
    d=ImageDraw.Draw(im);rr(d,box,r,fill=fill);rr(d,box,r,outline=border,width=2)
def circ(im,cx,cy,rad,color,glyph=None,gs=None):
    d=ImageDraw.Draw(im);d.ellipse([cx-rad,cy-rad,cx+rad,cy+rad],fill=color+(255,))
    if glyph: rich(d,(cx,cy-rad*0.72),glyph,emo(gs or int(rad)),emo(gs or int(rad)),(255,255,255,255),center=True)
def gsquare(size,c1,c2,r=28):
    arr=np.zeros((size,size,4),np.uint8)
    for y in range(size):
        f=y/size
        arr[y,:,0]=int(c1[0]*(1-f)+c2[0]*f);arr[y,:,1]=int(c1[1]*(1-f)+c2[1]*f);arr[y,:,2]=int(c1[2]*(1-f)+c2[2]*f);arr[y,:,3]=255
    img=Image.fromarray(arr,"RGBA");m=Image.new("L",(size,size),0);md=ImageDraw.Draw(m)
    md.rounded_rectangle([0,0,size-1,size-1],radius=r,fill=255);base=canvas(size,size);base.paste(img,(0,0),m);return base

# ---------------- builders: build(state) -> RGBA ----------------
def b_intro(st,acc):
    im=canvas(560);d=ImageDraw.Draw(im)
    cov=gsquare(300,PINK,(120,0,60));im.paste(cov,(310,20),cov)
    rich(d,(460,350),"hot girl bummer",bold(64),emo(64),(255,255,255,255),center=True)
    d.text((460,430),"blackbear",font=reg(40),fill=(180,180,185,255),anchor="mm")
    circ(im,460,500,40,acc,"▶️",46)
    return im
def b_block(st,acc):
    hits=st[0]; im=canvas(640);d=ImageDraw.Draw(im)
    d.text((60,20),"Recents",font=bold(50),fill=(255,255,255,255))
    names=[("you","📵"),("you 🙄","📵"),("you 💀","📵")]
    y=120
    for i,(nm,g) in enumerate(names):
        glass(im,[40,y,880,y+150],r=34)
        circ(im,130,y+75,46,(90,90,95) if i>=hits else RED)
        rich(d,(215,y+38),nm,bold(42),emo(42),(255,255,255,255))
        if i<hits:
            rr(d,[600,y+45,840,y+110],18,fill=RED+(255,)); rich(d,(720,y+58),"BLOCKED",bold(34),emo(34),(255,255,255,255),center=True)
        else:
            d.text((600,y+52),"missed call",font=reg(32),fill=(150,150,155,255))
        y+=170
    return im
def b_friends(st,acc):
    im=canvas(620);d=ImageDraw.Draw(im);glass(im,[30,20,890,600],r=44,fill=(20,20,22,242))
    rich(d,(460,52),"your friends 🙄",bold(46),emo(46),(255,255,255,255),center=True)
    d.line([60,135,860,135],fill=(255,255,255,28),width=2)
    def bub(y,t,right,col):
        w=rsize(d,t,reg(40),emo(40))[0]+70; x=860-w if right else 60
        rr(d,[x,y,x+w,y+88],26,fill=col); rich(d,(x+35,y+22),t,reg(40),emo(40),(255,255,255,255))
    bub(165,"you're so fake 💀",False,(58,58,60,255))
    bub(280,"k.",True,acc+(255,))
    # system messages
    d.text((460,400),"You left the group",font=reg(34),fill=(150,150,155,255),anchor="mm")
    d.text((460,450),"They removed you too",font=reg(34),fill=(150,150,155,255),anchor="mm")
    rich(d,(460,505),"🚫 mutual",bold(40),emo(40),(255,90,90,255),center=True)
    return im
def b_through(st,acc):
    fill=st[0]/20.0; im=canvas(440);d=ImageDraw.Draw(im);glass(im,[40,20,880,420],r=44,fill=(18,18,20,245))
    done=fill>=0.99
    rich(d,(460,70),"DONE ✓" if done else "I'M THROUGH",bold(64),emo(64),(LIME if done else (255,255,255))+(255,),center=True)
    rr(d,[100,210,820,270],30,fill=(55,55,60,255))
    if fill>0: rr(d,[100,210,100+int(720*fill),270],30,fill=acc+(255,))
    d.text((460,320),f"{int(fill*100)}%  •  unsubscribing…" if not done else "100%  •  blocked everywhere",
           font=reg(34),fill=(180,180,185,255),anchor="mm")
    return im
def b_music(st,acc):
    vol=st[0]/20.0; im=canvas(640);d=ImageDraw.Draw(im);glass(im,[40,20,880,620],r=46,fill=(18,18,20,246))
    cov=gsquare(300,PINK,(120,0,60));im.paste(cov,(310,60),cov)
    d.text((460,400),"hot girl bummer",font=bold(50),fill=(255,255,255,255),anchor="mm")
    d.text((460,450),"blackbear  •  now playing",font=reg(32),fill=(180,180,185,255),anchor="mm")
    # volume slider
    rich(d,(95,515),"🔈",emo(46),emo(46),(255,255,255,255))
    rr(d,[165,528,760,560],16,fill=(60,60,64,255)); rr(d,[165,528,165+int(595*vol),560],16,fill=acc+(255,))
    rich(d,(780,512),"🔊",emo(46),emo(46),(255,255,255,255))
    if vol>=0.99: rich(d,(460,585),"MAX 📢",bold(38),emo(38),acc+(255,),center=True)
    return im
def b_receipt(st,acc):
    im=canvas(480);d=ImageDraw.Draw(im);glass(im,[60,20,860,460],r=42,fill=(255,255,255,250))
    rich(d,(460,55),"  Pay",bold(46),emo(46),(0,0,0,255),center=True)
    d.line([100,140,820,140],fill=(0,0,0,30),width=2)
    rich(d,(110,180),"Birkin Bag 👜",bold(48),emo(48),(0,0,0,255))
    d.text((820,185),"$12,000",font=bold(48),fill=(0,0,0,255),anchor="ra")
    d.text((110,270),"Hermès • one-tap regret",font=reg(34),fill=(120,120,125,255))
    rr(d,[110,340,810,420],24,fill=(0,0,0,255)); rich(d,(460,358),"Paid 🤮",bold(44),emo(44),(255,255,255,255),center=True)
    return im
def b_match(st,acc):
    im=canvas(560);d=ImageDraw.Draw(im);glass(im,[40,20,880,540],r=46,fill=(20,12,18,248))
    rich(d,(460,50),"It's a Match! 🔥",bold(60),emo(60),PINK+(255,),center=True)
    circ(im,330,300,110,(80,80,90),"🙂",120); circ(im,590,300,110,acc,"😈",120)
    d.text((460,460),"you & someone random",font=reg(38),fill=(220,220,225,255),anchor="mm")
    return im
def b_social(st,acc):
    im=canvas(440);d=ImageDraw.Draw(im);glass(im,[120,20,800,420],r=48,fill=(20,20,22,246))
    rich(d,(460,60),"Social Battery",bold(46),emo(46),(255,255,255,255),center=True)
    rr(d,[230,170,690,250],18,outline=(255,255,255,200),width=5); d.rectangle([694,195,706,225],fill=(255,255,255,200))
    rr(d,[238,178,238+int(444*0.01)+30,242],10,fill=RED+(255,))
    rich(d,(460,300),"1% 🪫",bold(70),emo(70),RED+(255,),center=True)
    return im
def b_buylikes(st,acc):
    im=canvas(500);d=ImageDraw.Draw(im);glass(im,[80,40,840,460],r=42,fill=(36,36,40,250))
    rich(d,(460,70),"In-App Purchase",bold(40),emo(40),(255,255,255,255),center=True)
    rich(d,(460,160),"10,000 Likes 👍",bold(52),emo(52),(255,255,255,255),center=True)
    rich(d,(460,217),"+ Plump Lips Filter 💋",reg(36),emo(36),(190,190,195,255),center=True)
    rr(d,[230,320,690,400],26,fill=acc+(255,)); rich(d,(460,338),"Buy • $0.99",bold(44),emo(44),(0,0,0,255),center=True)
    return im
def b_shetext(st,acc):
    im=canvas(560);d=ImageDraw.Draw(im);glass(im,[30,20,890,540],r=44,fill=(20,20,22,242))
    rich(d,(460,48),"she 🙃",bold(46),emo(46),(255,255,255,255),center=True)
    d.line([60,130,860,130],fill=(255,255,255,28),width=2)
    def bub(y,t,right,col):
        w=rsize(d,t,reg(40),emo(40))[0]+70; x=860-w if right else 60
        rr(d,[x,y,x+w,y+88],26,fill=col); rich(d,(x+35,y+22),t,reg(40),emo(40),(255,255,255,255))
    bub(160,"i swear i'm single 😇",False,(58,58,60,255))
    bub(275,"you free? 👀",True,acc+(255,))
    # sneaky notification
    glass(im,[70,400,820,500],r=28,fill=(0,0,0,180))
    circ(im,150,450,38,RED,"❤️",44); rich(d,(220,418),"her man  • now",bold(32),emo(32),(255,255,255,255))
    rich(d,(220,460),"miss u babe 💍",reg(34),emo(34),(200,200,205,255))
    return im
def b_thursday(st,acc):
    im=canvas(440);d=ImageDraw.Draw(im);glass(im,[100,20,820,420],r=50,fill=(18,18,24,248))
    rich(d,(460,70),"🌙",emo(90),emo(90),(255,255,255,255),center=True)
    d.text((460,210),"Thursday",font=bold(64),fill=(255,255,255,255),anchor="mm")
    d.text((460,290),"11:47 PM",font=reg(48),fill=acc+(255,),anchor="mm")
    d.text((460,355),"hits different",font=reg(34),fill=(180,180,185,255),anchor="mm")
    return im
def b_playlist(st,acc):
    im=canvas(560);d=ImageDraw.Draw(im);glass(im,[40,20,880,540],r=44,fill=(18,22,18,248))
    cov=gsquare(180,GREEN,(10,60,30),r=24);im.paste(cov,(70,70),cov)
    rich(d,(290,90),"Daily Mix 🎧",bold(48),emo(48),(255,255,255,255))
    d.text((292,170),"college dropout music",font=reg(36),fill=(180,180,185,255))
    d.text((292,225),"every day, on repeat",font=reg(34),fill=(150,150,155,255))
    for i in range(3):
        y=320+i*70; circ(im,110,y+15,14,acc); d.text((160,y),["she be too thick","friends so annoying","but we go dumb"][i],font=reg(38),fill=(220,220,225,255))
    return im
def b_dumb(st,acc):
    im=canvas(440);d=ImageDraw.Draw(im)
    glass(im,[40,20,450,400],r=40,fill=(44,44,48,255))
    rich(d,(245,70),"🧠",emo(80),emo(80),(255,255,255,255),center=True)
    d.text((245,210),"Smart Mode",font=bold(38),fill=(210,210,215,255),anchor="mm");d.text((245,265),"OFF",font=reg(34),fill=(150,150,155,255),anchor="mm")
    glass(im,[470,20,880,400],r=40,fill=acc+(255,))
    rich(d,(675,70),"🤪",emo(80),emo(80),(0,0,0,255),center=True)
    d.text((675,210),"Dumb Mode",font=bold(38),fill=(0,0,0,255),anchor="mm");d.text((675,265),"ON",font=bold(34),fill=(0,0,0,255),anchor="mm")
    return im
def b_transfer(st,acc):
    im=canvas(460);d=ImageDraw.Draw(im);glass(im,[60,20,860,440],r=42,fill=(18,18,20,248))
    rich(d,(460,55),"Transfer Sent 🎲",bold(46),emo(46),(255,255,255,255),center=True)
    d.text((460,180),"-$10,000",font=bold(96),fill=RED+(255,),anchor="mm")
    d.text((460,300),"to: The Table",font=reg(40),fill=(190,190,195,255),anchor="mm")
    d.text((460,360),"just so we can be subdued",font=reg(32),fill=(140,140,145,255),anchor="mm")
    return im
def b_super(st,acc):
    im=canvas(440);d=ImageDraw.Draw(im);glass(im,[80,20,840,420],r=46,fill=(20,18,12,248))
    rich(d,(460,60),"💪",emo(90),emo(90),(255,255,255,255),center=True)
    rich(d,(460,210),"SUPERHUMAN",bold(58),emo(58),acc+(255,),center=True)
    d.text((460,300),"Energy",font=reg(38),fill=(190,190,195,255),anchor="mm")
    d.text((460,350),"999%",font=bold(52),fill=(255,255,255,255),anchor="mm")
    return im
def b_outro(st,acc):
    im=canvas(480);d=ImageDraw.Draw(im)
    rich(d,(460,40),"everybody hates 🖤",bold(60),emo(60),(255,255,255,255),center=True)
    rich(d,(460,120),"everybody",bold(60),emo(60),(255,255,255,255),center=True)
    glass(im,[170,250,750,370],r=60,fill=acc+(255,),border=(0,0,0,0))
    rich(d,(460,276),"Share this story 📲",bold(46),emo(46),(0,0,0,255),center=True)
    d.text((460,430),"made with Super Creator OS",font=reg(34),fill=(160,160,165,255),anchor="mm")
    return im

# scene table: (start, key, builder, caption, accent)
SC=[
 (0.00,"intro",b_intro,"hot girl bummer 🔥",PINK),
 (1.44,"block",b_block,"f*** you, and you, and you",RED),
 (4.52,"friends",b_friends,"i hate your friends — they hate me too",PINK),
 (8.96,"through",b_through,"i'm through, i'm through, i'm through",LIME),
 (11.72,"music",b_music,"hot girl bummer anthem — turn it UP 🔊",PINK),
 (20.12,"receipt",b_receipt,"throw up in your Birkin bag 👜",CYAN),
 (22.20,"match",b_match,"hook up with someone random 🔥",PINK),
 (23.64,"social",b_social,"social awkward — battery 1% 🪫",RED),
 (25.80,"buylikes",b_buylikes,"buy your lips and buy your likes 👍",VIOLET),
 (27.76,"shetext",b_shetext,"i swear she had a man 🙃",PINK),
 (29.12,"thursday",b_thursday,"hits different on a Thursday night 🌙",VIOLET),
 (31.46,"playlist",b_playlist,"college dropout music every day 🎧",GREEN),
 (34.92,"dumb",b_dumb,"we go dumb, yeah we go stupid 🤪",LIME),
 (38.50,"transfer",b_transfer,"10k on the table 🎲",RED),
 (42.20,"super",b_super,"one more line — i'm superhuman 💪",ORANGE),
 (44.88,"block2",b_block,"f*** you, and you, and you",RED),
 (49.58,"outro",b_outro,"i'm through 🖤",PINK),
]
TEND=51.0
# per-scene action onsets (absolute s) for punch + reveal counts
BLOCK_HITS=[2.02,3.12,4.00]; BLOCK2_HITS=[45.0,45.6,46.2]
THROUGH_HITS=[9.56,10.46,11.40]
ACTIONS=[2.02,3.12,4.00,5.82,8.44,9.56,10.46,11.40,14.58,16.04,19.74,20.12,22.20,23.64,25.80,27.76,29.12,31.46,34.92,38.50,42.20,44.88,45.6,46.2,49.58]
TANTRUM=[16.04,19.74]  # music shake windows

# ---------- audio envelope ----------
with wave.open(str(AUDIO),'rb') as w:
    sr=w.getframerate(); nch=w.getnchannels(); raw=w.readframes(w.getnframes())
a=np.frombuffer(raw,np.int16).astype(np.float32)
if nch==2: a=a.reshape(-1,2).mean(1)
a/=32768.0
NF=int(TEND*FPS)
env=np.zeros(NF)
win=int(sr/FPS)
for f in range(NF):
    i=int(f/FPS*sr); seg=a[i:i+win]
    env[f]=math.sqrt(float(np.mean(seg**2))+1e-9) if len(seg) else 0
env=env/ (np.percentile(env,95)+1e-9); env=np.clip(env,0,1.4)

# ---------- glow base ----------
G=560;gy,gx=np.mgrid[0:G,0:G];gd=np.sqrt((gx-G/2)**2+(gy-G/2)**2)/(G/2)
GLOW=(np.clip(1-gd,0,1)**2*255).astype(np.uint8)

# background
bgv=np.zeros((H,W,3),np.float32);yy,xx=np.mgrid[0:H,0:W]
dist=np.sqrt((xx-W/2)**2+(yy-H*0.42)**2)/(0.8*math.hypot(W/2,H/2))
bgv=(np.clip(1-dist,0,1)[...,None]*np.array([20,8,16])).astype(np.uint8)
BG=Image.fromarray(bgv,"RGB").convert("RGBA")

def status(d):
    d.text((60,46),"9:41",font=bold(40),fill=(255,255,255,255))
    bx=W-70; d.rounded_rectangle([bx-60,52,bx,84],6,outline=(255,255,255,200),width=3)
    d.rounded_rectangle([bx-56,56,bx-20,80],3,fill=(255,255,255,230)); d.rectangle([bx+2,60,bx+8,76],fill=(255,255,255,200))
    for i,hh in enumerate([10,16,22,28]): d.rounded_rectangle([bx-150+i*16,84-hh,bx-150+i*16+10,84],2,fill=(255,255,255,220))

# caption cache
def cap_img(text,acc):
    tmp=Image.new("RGBA",(W,150),(0,0,0,0));d=ImageDraw.Draw(tmp)
    w,_=rsize(d,text,bold(58),emo(58))
    if w>W-80:
        # shrink
        f=bold(46);ef=emo(46);w,_=rsize(d,text,f,ef)
    else: f=bold(58);ef=emo(58)
    rich(d,(W/2,30),text,f,ef,(255,255,255,255),center=True)
    rr(d,[W/2-w/2-8,108,W/2-w/2+min(w,140),120],6,fill=acc+(255,))
    return tmp
caps=[cap_img(c,a) for (_,_,_,c,a) in SC]

# card cache
_cardcache={}
def get_card(si):
    start,key,fn,cap,acc=SC[si]
    # dynamic state
    # compute at call-time via globals stashed
    st=_state
    ck=(si,st)
    if ck not in _cardcache:
        _cardcache[ck]=fn(st,acc)
    return _cardcache[ck]

def ease_out_back(x):
    c1=1.70158;c3=c1+1;return 1+c3*((x-1)**3)+c1*((x-1)**2)
def smooth(x):return x*x*(3-2*x)

starts=[s[0] for s in SC]
def scene_at(tt):
    si=0
    for i,s in enumerate(starts):
        if tt>=s: si=i
    return si

out=HERE/"hot_girl_bummer_uiedit.mp4"
cmd=["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s","%dx%d"%(W,H),"-r",str(FPS),"-i","-",
     "-i",str(AUDIO),"-c:v","libx264","-pix_fmt","yuv420p","-profile:v","high","-crf","19","-preset","medium",
     "-c:a","aac","-b:a","192k","-shortest",str(out)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
print("rendering %d frames..."%NF)
for f in range(NF):
    tt=f/FPS; si=scene_at(tt); start,key,fn,cap,acc=SC[si]
    nxt=starts[si+1] if si+1<len(starts) else TEND
    dur=nxt-start; local=tt-start; e=env[f]
    # dynamic state per scene
    if key=="block": st=(sum(1 for h in BLOCK_HITS if tt>=h),)
    elif key=="block2": st=(sum(1 for h in BLOCK2_HITS if tt>=h),)
    elif key=="through": st=(min(20,int(min(local/2.5,1.0)*20)),)
    elif key=="music":
        vol=0.55 if local<2.86 else min(1.0,0.55+(local-2.86)/0.4*0.45); st=(min(20,int(vol*20)),)
    else: st=(0,)
    global _state;_state=st
    card=_cardcache.get((si,st)) or fn(st,acc)
    _cardcache[(si,st)]=card
    frame=BG.copy()
    # glow (env-driven)
    gsz=int(560+e*220)
    gi=Image.new("RGBA",(gsz,gsz),acc+(0,)); al=Image.fromarray(GLOW,"L").resize((gsz,gsz)).point(lambda p:int(p*(0.10+0.22*e)))
    gi.putalpha(al); frame.alpha_composite(gi,(int(W/2-gsz/2),int(CARD_CY-gsz/2)))
    # card transform
    cw,ch=card.size
    tin=0.20; tout=0.14
    if local<tin: p=local/tin; ee=ease_out_back(min(p,1)); scale=0.80+0.20*ee; alpha=smooth(min(p,1)); dy=(1-smooth(min(p,1)))*60
    elif local>dur-tout: p=(local-(dur-tout))/tout; scale=1.0-0.05*p; alpha=1-smooth(min(p,1)); dy=-smooth(min(p,1))*30
    else: scale=1.0+0.03*e; alpha=1.0; dy=math.sin(tt*2)*4
    # action punch
    dmin=min((abs(tt-h) for h in ACTIONS),default=9)
    if dmin<0.18: scale+= 0.05*math.exp(-dmin*16)
    # tantrum shake
    shx=shy=0
    for ts in TANTRUM:
        if 0<=tt-ts<0.5: amp=18*math.exp(-(tt-ts)*6); shx=int(math.sin(tt*70)*amp); shy=int(math.cos(tt*60)*amp)
    nw,nh=max(1,int(cw*scale)),max(1,int(ch*scale)); cim=card.resize((nw,nh))
    if alpha<1: cim.putalpha(cim.split()[3].point(lambda p:int(p*alpha)))
    frame.alpha_composite(cim,(int(W/2-nw/2)+shx,int(CARD_CY-nh/2+dy)+shy))
    # caption
    capim=caps[si]
    if local<0.12: ca=smooth(local/0.12)
    elif local>dur-tout: ca=1-smooth(min((local-(dur-tout))/tout,1))
    else: ca=1.0
    if ca>0:
        ci=capim if ca>=1 else capim.copy()
        if ca<1: ci.putalpha(ci.split()[3].point(lambda p:int(p*ca)))
        frame.alpha_composite(ci,(0,1500+int((1-ca)*16)))
    d=ImageDraw.Draw(frame)
    pw=int((tt/TEND)*(W-120)); d.rounded_rectangle([60,70,W-60,78],4,fill=(255,255,255,40)); d.rounded_rectangle([60,70,60+pw,78],4,fill=acc+(255,))
    d.text((W/2,1850),"@phone.goes.brrr",font=reg(32),fill=(150,150,155,255),anchor="mm")
    proc.stdin.write(frame.convert("RGB").tobytes())
    if f%150==0: print("  %d/%d"%(f,NF))
proc.stdin.close();proc.wait();print("DONE ->",out)
