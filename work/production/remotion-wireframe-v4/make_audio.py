import math,wave,struct,random
from pathlib import Path
SR=48000; DUR=56.266667; N=int(SR*DUR); random.seed(22)
L=[0.0]*N; R=[0.0]*N

def add(t,dur,fn,g=1.0,pan=0.0):
 a=max(0,int(t*SR)); b=min(N,a+int(dur*SR)); gl=g*(1-pan); gr=g*(1+pan)
 for i in range(a,b):
  x=(i-a)/SR; s=fn(x); L[i]+=s*gl; R[i]+=s*gr

def osc(f,dec=1.0):
 return lambda x: math.sin(2*math.pi*f*x)*math.exp(-dec*x)
def chord(fs):
 return lambda x: sum(math.sin(2*math.pi*f*x) for f in fs)/len(fs)*math.exp(-0.16*x)
def click(x): return ((random.random()*2-1)*math.exp(-70*x)+0.25*math.sin(2*math.pi*1900*x)*math.exp(-80*x))
# lo-fi tech bed
bpm=96; beat=60/bpm; bar=beat*4; prog=[[73.42,146.83,220],[65.41,130.81,196],[58.27,116.54,174.61],[55,110,164.81]]
for k in range(int(DUR/bar)+2):
 add(k*bar,bar,chord(prog[k%4]),0.10,0)
 root=prog[k%4][0]
 for j in range(4): add(k*bar+j*beat,beat*0.65,osc(root,2.4),0.065,0)
# per scene pulse + UI click accents
scene_times=[0,7,13.5,19.5,25.5,33,40,46.5,52]
for t in scene_times:
 add(t,0.16,click,0.10,0)
 add(max(0,t-0.20),0.20,osc(820,10),0.055,0)
# high plucks
notes=[293.66,349.23,440,523.25,587.33,523.25,440,349.23]
step=beat/2
for i in range(int(DUR/step)):
 add(i*step,step*0.55,osc(notes[i%len(notes)],6),0.025,0.25 if i%2 else -0.25)
# subtle noise bed
for i in range(N):
 n=(random.random()*2-1)*0.003; L[i]+=n; R[i]+=n
mx=max(max(abs(x) for x in L),max(abs(x) for x in R),1e-9); s=0.72/mx
p=Path('public/audio'); p.mkdir(parents=True,exist_ok=True)
with wave.open(str(p/'original_score.wav'),'wb') as w:
 w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
 data=bytearray()
 for i in range(N):
  data+=struct.pack('<hh',int(max(-1,min(1,L[i]*s))*32767),int(max(-1,min(1,R[i]*s))*32767))
 w.writeframes(data)
print(p/'original_score.wav')
