"""build_video.py — "PHONE GOES BRRR" fake phone-UI lyric edit.
Original design (Super Creator OS). Vertical 1080x1920, 30fps, ~48s.
All UI cards drawn with Pillow; animated + beat-synced; piped to ffmpeg with music.wav.
"""
import numpy as np, subprocess, math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).parent
W, H, FPS = 1080, 1920, 30
BPM = 120; BEAT = 60.0/BPM
ACCENTS = [(0,229,255),(255,45,155),(200,255,0),(139,92,246),(255,138,0),(0,224,150)]

# ---------- fonts ----------
FD = "C:/Windows/Fonts/"
_fc = {}
def F(name, size):
    key=(name,size)
    if key not in _fc: _fc[key]=ImageFont.truetype(FD+name, size)
    return _fc[key]
def bold(s): return F("arialbd.ttf", s)
def reg(s):  return F("arial.ttf", s)
def emo(s):  return F("seguiemj.ttf", s)

def is_emoji(ch):
    o=ord(ch)
    return (0x1F000<=o<=0x1FAFF) or (0x2600<=o<=0x27BF) or (0x2B00<=o<=0x2BFF) or o in (0x2934,0x2935) or (0x1F1E6<=o<=0x1F1FF)

def rich_size(draw, text, font, efont):
    w=0; h=0
    for ch in text:
        if ch=='️': continue
        f = efont if is_emoji(ch) else font
        bb=draw.textbbox((0,0),ch,font=f)
        w+= bb[2]-bb[0]; h=max(h,bb[3]-bb[1])
    return w,h

def draw_rich(draw, xy, text, font, efont, fill, center=False):
    x,y=xy
    if center:
        w,_=rich_size(draw,text,font,efont); x-=w/2
    for ch in text:
        if ch=='️': continue
        if is_emoji(ch):
            try:
                draw.text((x,y),ch,font=efont,embedded_color=True)
                bb=draw.textbbox((0,0),ch,font=efont); x+=bb[2]-bb[0]
            except Exception:
                bb=draw.textbbox((0,0),ch,font=font); x+=bb[2]-bb[0]
        else:
            draw.text((x,y),ch,font=font,fill=fill)
            bb=draw.textbbox((0,0),ch,font=font); x+=bb[2]-bb[0]

# ---------- primitives ----------
def card_canvas(h, w=880):
    return Image.new("RGBA",(w,h),(0,0,0,0))

def rrect(d, box, r, fill=None, outline=None, width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def glass(im, box, r=40, fill=(28,28,30,235), border=(255,255,255,28)):
    d=ImageDraw.Draw(im); rrect(d,box,r,fill=fill); rrect(d,box,r,outline=border,width=2)

def icon(im, cx, cy, rad, color, glyph=None, gfont=None, gcolor=(255,255,255,255)):
    d=ImageDraw.Draw(im)
    d.ellipse([cx-rad,cy-rad,cx+rad,cy+rad], fill=color+(255,))
    if glyph:
        draw_rich(d,(cx,cy-rad*0.7),glyph,gfont or bold(int(rad)),emo(int(rad*1.2)),gcolor,center=True)

def grad_square(size, c1, c2, r=28):
    base=Image.new("RGBA",(size,size),(0,0,0,0))
    arr=np.zeros((size,size,4),np.uint8)
    for y in range(size):
        f=y/size
        arr[y,:,0]=int(c1[0]*(1-f)+c2[0]*f)
        arr[y,:,1]=int(c1[1]*(1-f)+c2[1]*f)
        arr[y,:,2]=int(c1[2]*(1-f)+c2[2]*f)
        arr[y,:,3]=255
    img=Image.fromarray(arr,"RGBA")
    mask=Image.new("L",(size,size),0); md=ImageDraw.Draw(mask)
    md.rounded_rectangle([0,0,size-1,size-1],radius=r,fill=255)
    base.paste(img,(0,0),mask); return base

# ---------- card builders (return RGBA image) ----------
def c_lock(acc):
    im=card_canvas(560)
    d=ImageDraw.Draw(im)
    draw_rich(d,(440,10),"7:00",bold(190),emo(190),(255,255,255,255),center=True)
    draw_rich(d,(440,220),"Saturday, June 16",reg(40),emo(40),(190,190,195,255),center=True)
    glass(im,[60,320,820,520],r=36)
    icon(im,140,420,52,acc,"⏰",emo(60))
    d.text((230,360),"ALARM  •  now",font=reg(30),fill=(170,170,175,255))
    draw_rich(d,(230,398),"WAKE UP — it's the weekend 😤",reg(40),emo(40),(255,255,255,255))
    return im

def c_notifs(acc):
    im=card_canvas(640);
    rows=[((52,199,89),"Messages","Mom: did you eat yet? 🍜"),
          ((255,45,155),"Instagram","khun_x and 11 others liked your post"),
          ((10,132,255),"Mail","3 new — all ignored")]
    y=20
    for col,app,msg in rows:
        glass(im,[40,y,840,y+180],r=34)
        icon(im,130,y+90,50,col)
        d=ImageDraw.Draw(im)
        d.text((215,y+42),app+"  • now",font=bold(34),fill=(255,255,255,255))
        draw_rich(d,(215,y+92),msg,reg(34),emo(34),(200,200,205,255))
        y+=210
    return im

def c_chat(acc):
    im=card_canvas(700)
    glass(im,[30,20,850,680],r=44,fill=(20,20,22,240))
    d=ImageDraw.Draw(im)
    draw_rich(d,(440,52),"The Squad 🔥",bold(46),emo(46),(255,255,255,255),center=True)
    d.line([60,135,820,135],fill=(255,255,255,30),width=2)
    def bubble(y,text,right,col):
        w=rich_size(d,text,reg(40),emo(40))[0]+70
        if right: x=820-w
        else: x=60
        rrect(d,[x,y,x+w,y+90],28,fill=col)
        draw_rich(d,(x+35,y+24),text,reg(40),emo(40),(255,255,255,255))
    bubble(170,"you free tonight??",False,(58,58,60,255))
    bubble(290,"always 😎",True,acc+(255,))
    bubble(410,"pull up 8pm 📍",False,(58,58,60,255))
    bubble(530,"bet. 🔋100%",True,acc+(255,))
    return im

def c_music(acc):
    im=card_canvas(720)
    glass(im,[40,20,840,700],r=46,fill=(18,18,20,245))
    d=ImageDraw.Draw(im)
    cov=grad_square(360,acc,(255,45,155))
    im.paste(cov,(260,60),cov)
    d.text((440,460),"Weekend Mode",font=bold(52),fill=(255,255,255,255),anchor="mm")
    d.text((440,510),"CLAUDE • Super Creator OS",font=reg(34),fill=(180,180,185,255),anchor="mm")
    # progress
    rrect(d,[120,565,760,575],6,fill=(80,80,85,255))
    rrect(d,[120,565,120+int(640*0.42),575],6,fill=acc+(255,))
    d.text((120,590),"1:24",font=reg(26),fill=(160,160,165,255))
    d.text((760,590),"-2:01",font=reg(26),fill=(160,160,165,255),anchor="ra")
    # transport
    for cx,g in [(330,"⏮"),(440,"⏸"),(550,"⏭")]:
        draw_rich(d,(cx,648),g,emo(46),emo(46),(255,255,255,255),center=True)
    return im

def c_maps(acc):
    im=card_canvas(640)
    glass(im,[30,20,850,560],r=44,fill=(22,26,24,245))
    d=ImageDraw.Draw(im)
    # route
    pts=[(120,470),(260,360),(380,400),(540,230),(700,260),(780,140)]
    d.line(pts,fill=acc+(255,),width=14,joint="curve")
    d.ellipse([100,450,140,490],fill=(255,255,255,255))
    draw_rich(d,(760,90),"📍",emo(70),emo(70),(255,255,255,255),center=True)
    glass(im,[60,40,520,200],r=30,fill=(0,0,0,160))
    d.text((90,70),"8 min",font=bold(70),fill=acc+(255,))
    d.text((92,160),"to The Party • arrive 8:14",font=reg(32),fill=(200,200,205,255))
    return im

def c_todo(acc):
    im=card_canvas(560)
    glass(im,[40,20,840,540],r=42,fill=(20,20,22,245))
    d=ImageDraw.Draw(im)
    draw_rich(d,(80,50),"Tonight ✓",bold(50),emo(50),(255,255,255,255))
    items=[("charge phone",True),("grab the keys",True),("zero responsibilities",True),("good vibes only",False)]
    y=170
    for txt,done in items:
        col=acc if done else (90,90,95)
        if done: d.ellipse([80,y,124,y+44],fill=col+(255,)); draw_rich(d,(102,y-2),"✓",bold(36),emo(36),(0,0,0,255),center=True)
        else: d.ellipse([80,y,124,y+44],outline=col+(255,),width=4)
        tc=(120,120,125,255) if done else (255,255,255,255)
        d.text((160,y+2),txt,font=reg(42),fill=tc)
        if done:
            w=d.textbbox((160,y+2),txt,font=reg(42)); d.line([160,y+24,w[2],y+24],fill=(120,120,125,255),width=4)
        y+=88
    return im

def c_poll(acc):
    im=card_canvas(560)
    glass(im,[40,30,840,520],r=44,fill=(18,18,20,245))
    d=ImageDraw.Draw(im)
    d.text((440,110),"going out tonight?",font=bold(54),fill=(255,255,255,255),anchor="mm")
    # YES bar 92%
    rrect(d,[90,200,790,290],26,fill=(50,50,54,255))
    rrect(d,[90,200,90+int(700*0.92),290],26,fill=acc+(255,))
    d.text((120,215),"YES",font=bold(48),fill=(0,0,0,255)); d.text((760,215),"92%",font=bold(44),fill=(0,0,0,255),anchor="ra")
    # nah 8%
    rrect(d,[90,330,790,420],26,fill=(50,50,54,255))
    rrect(d,[90,330,90+int(700*0.08),420],26,fill=(90,90,95,255))
    d.text((120,345),"nah",font=bold(48),fill=(220,220,225,255)); d.text((760,345),"8%",font=bold(44),fill=(180,180,185,255),anchor="ra")
    d.text((440,470),"1,204 votes",font=reg(32),fill=(160,160,165,255),anchor="mm")
    return im

def c_dnd(acc):
    im=card_canvas(560)
    d=ImageDraw.Draw(im)
    tiles=[("Do Not Disturb","🌙",True),("Airplane","✈","off"),("Wi-Fi","📶",True),("Focus","🎯",True)]
    pos=[(40,20),(460,20),(40,300),(460,300)]
    for (lbl,g,on),(x,y) in zip(tiles,pos):
        col=acc if on==True else (60,60,64)
        glass(im,[x,y,x+380,y+240],r=40,fill=col+(255,) if on==True else (44,44,48,255))
        dd=ImageDraw.Draw(im)
        draw_rich(dd,(x+40,y+40),g,emo(70),emo(70),(0,0,0,255) if on==True else (200,200,205,255))
        dd.text((x+40,y+150),lbl,font=bold(34),fill=(0,0,0,255) if on==True else (210,210,215,255))
        dd.text((x+40,y+195),"ON" if on==True else "OFF",font=reg(28),fill=(0,0,0,200) if on==True else (150,150,155,255))
    return im

def c_camera(acc):
    im=card_canvas(680)
    d=ImageDraw.Draw(im)
    glass(im,[40,20,840,560],r=40,fill=(12,12,14,255))
    # viewfinder corners
    for cx,cy in [(110,90),(770,90),(110,490),(770,490)]:
        l=46
        d.line([cx,cy,cx+(l if cx<440 else -l),cy],fill=acc+(255,),width=8)
        d.line([cx,cy,cx,cy+(l if cy<300 else -l)],fill=acc+(255,),width=8)
    draw_rich(d,(440,210),"📸",emo(150),emo(150),(255,255,255,255),center=True)
    d.text((440,400),"+24 photos tonight",font=bold(44),fill=(255,255,255,255),anchor="mm")
    # shutter
    d.ellipse([390,600,490,700],outline=(255,255,255,255),width=8)
    d.ellipse([404,614,476,686],fill=acc+(255,))
    return im

def c_grid(acc):
    im=card_canvas(680)
    apps=[((52,199,89),"💬"),((255,45,155),"📷"),((10,132,255),"🎵"),
          ((255,138,0),"🗺"),(acc,"⚡"),((175,82,222),"🎮"),
          ((255,59,48),"❤"),((90,200,250),"☁"),((255,204,0),"⭐")]
    d=ImageDraw.Draw(im)
    s=240; gap=30; x0=40; y0=20
    for i,(col,g) in enumerate(apps):
        r=i//3; c=i%3
        x=x0+c*(s+gap); y=y0+r*(s-40+gap)
        rrect(d,[x,y,x+s,y+s-40],46,fill=col+(255,))
        draw_rich(d,(x+s/2,y+(s-40)/2-60),g,emo(110),emo(110),(255,255,255,255),center=True)
    return im

def c_share(acc):
    im=card_canvas(560)
    d=ImageDraw.Draw(im)
    draw_rich(d,(440,30),"that's a wrap ✨",bold(72),emo(72),(255,255,255,255),center=True)
    glass(im,[150,200,730,330],r=64,fill=acc+(255,),border=(0,0,0,0))
    draw_rich(d,(440,228),"Share this story  📲",bold(50),emo(50),(0,0,0,255),center=True)
    d.text((440,420),"made with  Super Creator OS",font=reg(38),fill=(170,170,175,255),anchor="mm")
    return im

SCENES=[
 (c_lock,   "another day. let's GO",        4.5),
 (c_notifs, "phone already blowin' up 📲",  4.0),
 (c_chat,   "the squad's got plans",        4.0),
 (c_music,  "turn it UP 🔊",                4.0),
 (c_maps,   "we on the way 🚗",             4.0),
 (c_todo,   "checklist? done ✅",           4.0),
 (c_poll,   "you already know 😎",          4.0),
 (c_dnd,    "DND — we ghost 👻",            4.0),
 (c_camera, "memories loading…",            4.0),
 (c_grid,   "all in one place ✨",          4.0),
 (c_share,  "❤️  drop a like",              3.5),
]

# ---------- precompute ----------
print("pre-rendering cards...")
cards=[]
for i,(fn,cap,dur) in enumerate(SCENES):
    acc=ACCENTS[i%len(ACCENTS)]
    cards.append((fn(acc),cap,dur,acc))

# background: subtle radial vignette on near-black
bg=np.zeros((H,W,3),np.float32)
yy,xx=np.mgrid[0:H,0:W]
cx,cy=W/2,H*0.42
dist=np.sqrt((xx-cx)**2+(yy-cy)**2)/ (0.75*math.hypot(W/2,H/2))
vig=np.clip(1-dist,0,1)
base_bg=(vig[...,None]*np.array([14,14,18])).astype(np.uint8)
BG=Image.fromarray(base_bg,"RGB").convert("RGBA")

# glow blob
G=600
gy,gx=np.mgrid[0:G,0:G]
gd=np.sqrt((gx-G/2)**2+(gy-G/2)**2)/(G/2)
galpha=np.clip(1-gd,0,1)**2
GLOW=(galpha*255).astype(np.uint8)

def caption_img(text,acc):
    tmp=Image.new("RGBA",(W,160),(0,0,0,0)); d=ImageDraw.Draw(tmp)
    w,_=rich_size(d,text,bold(64),emo(64))
    draw_rich(d,(W/2,40),text,bold(64),emo(64),(255,255,255,255),center=True)
    # accent underline
    d.rounded_rectangle([W/2-w/2-10,120,W/2-w/2+min(w,120),132],6,fill=acc+(255,))
    return tmp
caps=[caption_img(c,a) for (_,c,_,a) in cards]

def ease_out_back(x):
    c1=1.70158; c3=c1+1
    return 1+c3*((x-1)**3)+c1*((x-1)**2)
def smooth(x): return x*x*(3-2*x)

# scene start times
starts=[]; tacc=0
for _,_,dur,_ in cards: starts.append(tacc); tacc+=dur
TOTAL=tacc
NF=int(TOTAL*FPS)
print("total %.1fs, %d frames"%(TOTAL,NF))

# status bar (static) — draw per frame fresh (cheap) for the clock blink
def draw_status(d):
    d.text((60,46),"9:41",font=bold(40),fill=(255,255,255,255))
    # right: signal dots, wifi, battery
    bx=W-70
    d.rounded_rectangle([bx-60,52,bx,84],6,outline=(255,255,255,200),width=3)
    d.rounded_rectangle([bx-56,56,bx-20,80],3,fill=(255,255,255,230))
    d.rectangle([bx+2,60,bx+8,76],fill=(255,255,255,200))
    for i,h in enumerate([10,16,22,28]):
        d.rounded_rectangle([bx-150+i*16,84-h,bx-150+i*16+10,84],2,fill=(255,255,255,220))

# ---------- ffmpeg pipe ----------
out=HERE/"phone_goes_brrr.mp4"
cmd=["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s","%dx%d"%(W,H),"-r",str(FPS),"-i","-",
     "-i",str(HERE/"music.wav"),
     "-c:v","libx264","-pix_fmt","yuv420p","-profile:v","high","-crf","19","-preset","medium",
     "-c:a","aac","-b:a","192k","-shortest",str(out)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)

CARD_CY=760
for f in range(NF):
    tt=f/FPS
    # active scene
    si=0
    for i in range(len(cards)):
        if tt>=starts[i]: si=i
    card,cap,dur,acc=cards[si]; cs=starts[si]; local=tt-cs
    frame=BG.copy()
    # beat glow
    phase=(tt%BEAT)/BEAT
    pulse=math.exp(-phase*3.2)
    gsize=int(620+pulse*180)
    gimg=Image.new("RGBA",(gsize,gsize),acc+(0,))
    a=Image.fromarray(GLOW,"L").resize((gsize,gsize))
    a=a.point(lambda p:int(p*(0.16+0.18*pulse)))
    gimg.putalpha(a)
    frame.alpha_composite(gimg,(int(W/2-gsize/2),int(CARD_CY-gsize/2)))
    # card transform
    cw,ch=card.size
    tin=0.42; tout=0.28
    if local<tin:
        p=local/tin; e=ease_out_back(min(p,1)); scale=0.86+0.14*e; alpha=smooth(min(p,1)); dy=(1-smooth(min(p,1)))*70
    elif local>dur-tout:
        p=(local-(dur-tout))/tout; scale=1.0-0.05*p; alpha=1-smooth(min(p,1)); dy=-smooth(min(p,1))*40
    else:
        # gentle idle float + beat nudge
        scale=1.0+0.012*pulse; alpha=1.0; dy=math.sin(tt*1.6)*5
    nw,nh=max(1,int(cw*scale)),max(1,int(ch*scale))
    cim=card.resize((nw,nh))
    if alpha<1:
        al=cim.split()[3].point(lambda p:int(p*alpha)); cim.putalpha(al)
    frame.alpha_composite(cim,(int(W/2-nw/2),int(CARD_CY-nh/2+dy)))
    # caption
    capim=caps[si]
    if local<0.15:
        ca=smooth(local/0.15)
    elif local>dur-tout:
        ca=1-smooth(min((local-(dur-tout))/tout,1))
    else: ca=1.0
    if ca>0:
        ci=capim.copy()
        if ca<1: ci.putalpha(ci.split()[3].point(lambda p:int(p*ca)))
        frame.alpha_composite(ci,(0,1500+int((1-ca)*20)))
    # overlays
    d=ImageDraw.Draw(frame)
    draw_status(d)
    # progress bar
    pw=int((tt/TOTAL)*(W-120))
    d.rounded_rectangle([60,120,W-60,128],4,fill=(255,255,255,40))
    d.rounded_rectangle([60,120,60+pw,128],4,fill=acc+(255,))
    # handle
    d.text((W/2,1850),"@phone.goes.brrr",font=reg(34),fill=(150,150,155,255),anchor="mm")
    proc.stdin.write(frame.convert("RGB").tobytes())
    if f%120==0: print("  frame %d/%d"%(f,NF))

proc.stdin.close(); proc.wait()
print("DONE ->",out)
