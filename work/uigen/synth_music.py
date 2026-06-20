"""synth_music.py — original royalty-free upbeat pop/EDM bed for the UI lyric edit.
120 BPM, A-minor, progression Am-F-C-G. All synthesized with numpy (no samples).
Output: work/uigen/music.wav  (~48s, 44.1kHz stereo).
"""
import numpy as np, wave, struct, sys
from pathlib import Path

SR = 44100
BPM = 120
BEAT = 60.0 / BPM          # 0.5s
BAR = BEAT * 4             # 2.0s
BARS = 24                  # 48s
TOTAL = BAR * BARS
N = int(TOTAL * SR)
t = np.arange(N) / SR

def env(length, a=0.005, d=0.08, s=0.0, r=0.05, sus=0.7):
    n = int(length * SR)
    out = np.zeros(n)
    ai = int(a*SR); di = int(d*SR); ri = int(r*SR)
    ai=max(ai,1); di=max(di,1); ri=max(ri,1)
    out[:ai] = np.linspace(0,1,ai)
    out[ai:ai+di] = np.linspace(1,sus,di)
    hold = n-ai-di-ri
    if hold>0: out[ai+di:ai+di+hold]=sus
    out[-ri:] = np.linspace(out[-ri-1] if n>ri else sus,0,ri)
    return out

def saw(freq, length, detune=0.0):
    n=int(length*SR); tt=np.arange(n)/SR
    s=np.zeros(n)
    for h in range(1,12):
        s+= (1.0/h)*np.sin(2*np.pi*freq*(1+detune)*h*tt)
    return s/np.max(np.abs(s)+1e-9)

def sine(freq,length):
    n=int(length*SR); tt=np.arange(n)/SR
    return np.sin(2*np.pi*freq*tt)

def add(buf, sig, at):
    i=int(at*SR); j=min(len(buf), i+len(sig))
    buf[i:j]+=sig[:j-i]

NOTE={'A2':110.0,'F2':87.31,'C3':130.81,'G2':98.0,
      'A3':220.0,'C4':261.63,'E4':329.63,'F3':174.61,
      'G3':196.0,'B3':246.94,'D4':293.66,'G4':392.0,'E5':659.25,'A4':440.0,'C5':523.25}
# chord per bar (root for bass, triad for pad/lead)
PROG=[('A2',['A3','C4','E4']),('F2',['F3','A3','C4']),
      ('C3',['C4','E4','G4']),('G2',['G3','B3','D4'])]

L=np.zeros(N); R=np.zeros(N)

def kick(at):
    n=int(0.18*SR); tt=np.arange(n)/SR
    f=120*np.exp(-tt*22)+48
    s=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-tt*9)
    add(L,s*0.9,at); add(R,s*0.9,at)

def hat(at, open=False):
    dur=0.12 if open else 0.04
    n=int(dur*SR); noise=np.random.uniform(-1,1,n)
    e=np.exp(-np.arange(n)/SR*(35 if open else 90))
    s=noise*e*0.22
    add(L,s,at); add(R,s,at)

def clap(at):
    n=int(0.14*SR); noise=np.random.uniform(-1,1,n)
    e=np.exp(-np.arange(n)/SR*22)
    s=noise*e*0.35
    add(L,s,at); add(R,s,at)

for bar in range(BARS):
    root,triad=PROG[bar%4]
    bt=bar*BAR
    # drums (drop in after 2-bar intro)
    full = bar>=2
    for b in range(4):
        at=bt+b*BEAT
        if full: kick(at)
        hat(at+BEAT/2, open=(b==3))
        hat(at)
        if full and b in (1,3): clap(at)
    # bass (root, eighth-note pulse)
    if bar>=2:
        for e8 in range(8):
            at=bt+e8*(BEAT/2)
            bs=saw(NOTE[root],BEAT/2,detune=0.001)*env(BEAT/2,a=0.004,d=0.05,sus=0.6,r=0.04)
            bs*=0.32
            add(L,bs,at); add(R,bs,at)
    # pad chord (whole bar, soft)
    for nm in triad:
        p=saw(NOTE[nm]*0.5,BAR,detune=0.004)*env(BAR,a=0.06,d=0.3,sus=0.45,r=0.25)*0.06
        add(L,p,bt); add(R,p,bt+0.004)  # tiny stereo
    # lead arpeggio (eighths) after intro
    if bar>=4:
        arp=triad+[triad[1]]  # 4 notes pattern over 8 eighths (x2)
        seq=[triad[0],triad[1],triad[2],triad[1]]*2
        for e8,nm in enumerate(seq):
            at=bt+e8*(BEAT/2)
            ld=saw(NOTE[nm]*2,BEAT/2,detune=0.002)*env(BEAT/2,a=0.003,d=0.06,sus=0.3,r=0.05)
            ld*=0.12
            add(L,ld,at-0.0); add(R,ld,at)

# master: gentle highpass on hats already; soft limit + normalize
def softlimit(x):
    return np.tanh(x*1.1)
L=softlimit(L); R=softlimit(R)
peak=max(np.max(np.abs(L)),np.max(np.abs(R)),1e-9)
L=L/peak*0.95; R=R/peak*0.95
# fade in/out
fi=int(0.05*SR); fo=int(0.6*SR)
for ch in (L,R):
    ch[:fi]*=np.linspace(0,1,fi); ch[-fo:]*=np.linspace(1,0,fo)

stereo=np.empty(N*2)
stereo[0::2]=L; stereo[1::2]=R
data=(stereo*32767).astype(np.int16)
out=Path(__file__).parent/'music.wav'
with wave.open(str(out),'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(data.tobytes())
print('wrote',out,'dur=%.2fs'%TOTAL)
