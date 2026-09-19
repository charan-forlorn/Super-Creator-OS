import React from 'react';
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig, Easing} from 'remotion';

const C={bg:'#000000',surface:'#121a13',surface2:'#182018',surface3:'#0b100c',line:'#2c3a2d',text:'#edf1eb',muted:'#899689',green:'#b9e58a',green2:'#7bd45a'};

const states=[
  {s:0,e:2.0,title:'Google',query:'show me a cleaner way to automate this',rows:['Automation playbook','3 steps · ready to run'],button:'OPEN RESULT'},
  {s:2.0,e:4.0,title:'Liked Songs',query:'Spotify',rows:['Paradise','Focus playlist','Close All'],chips:['Spotify']},
  {s:4.0,e:6.0,title:'Paradise',query:'replay',rows:['Paradise · Now Playing','03:02','Recommended next'],chips:['Spotify']},
  {s:6.0,e:8.0,title:'Gemini',query:'Hi Subhan',rows:["You don’t have to…",'assistant result','ready'],chips:['Gemini']},
  {s:8.0,e:10.0,title:'Today',query:'Tell me what you’re here for?',rows:['Today','Schedule · 16:23','Focus block'],chips:['Today']},
  {s:10.0,e:12.0,title:'Today',query:'Tell me what you’re here for?',rows:['16:23 · calendar conflict','18:00 · focus block','Here for?'],chips:['Today']},
  {s:12.0,e:14.0,title:'Today',query:'',rows:['Inbox','Tasks','Calendar'],chips:['Today']},
  {s:14.0,e:16.0,title:'Today',query:'',rows:['Inbox','Calendar','Focus'],chips:['Today']},
  {s:16.0,e:18.0,title:'Inbox',query:'Mobile Legend',rows:['Spotify','Todoist','ChatGPT','CapCut'],chips:['Inbox','Mobile Legend']},
  {s:18.0,e:20.0,title:'Today',query:'Alight Motion',rows:['Inbox','Social Media','Mobile Legend','Lumo'],chips:['Today','Alight Motion']},
  {s:20.0,e:22.0,title:'Disappear',query:'',rows:['Tap to disappear','Message controls','Close all'],chips:['Messages']},
  {s:22.0,e:24.0,title:'Quick Actions',query:'',rows:['Wi‑Fi','Airplane','Personal','Do Not Disturb','Hotspot'],chips:['SYSTEM']},
  {s:24.0,e:26.0,title:'Apps',query:'',rows:['Spotify','Todoist','ChatGPT','CapCut'],chips:['TOOLS']},
  {s:26.0,e:28.0,title:'Recommended Stations',query:'RADIO',rows:['LE SSERAFIM','NewJeans, ILLIT, IU','Eenie Meenie'],chips:['RADIO','HOLD']},
  {s:28.0,e:30.0,title:'Calendar now',query:'Dancin\'g',rows:['12:00–14:00','Calendar','Today'],chips:['CALENDAR']},
  {s:30.0,e:32.0,title:'Music now',query:'Sean Kingston',rows:['Tasks · 09:00','Mark completed','Reschedule today'],chips:['TASKS']},
  {s:32.0,e:34.0,title:'Mind',query:'',rows:['Focus','Breathing','Reset'],chips:['MIND']},
  {s:34.0,e:36.0,title:'Digital Wellbeing',query:'Please don’t waste my…',rows:['Today · 7hr 09m','Alight Motion','Your Digital Wellbeing tools'],chips:['TODAY']},
  {s:36.0,e:38.0,title:'Lock Apps',query:'Tap the lock button to lock an app',rows:['and it will not be cleaned up','when you close all recent apps','Close all'],chips:['LOCK']},
  {s:38.0,e:40.0,title:'Lumo',query:'Not Trying to Re-',rows:['Sean Kingston · Justin Bieber','Eenie Meenie','Close all'],chips:['MUSIC']},
  {s:40.0,e:42.0,title:'STAY',query:'',rows:['00:01','03:02','Kid LAROI · Justin Bieber'],chips:['NOW PLAYING']},
  {s:42.0,e:44.0,title:'Lyrics',query:'',rows:['STAY','next line','music state'],chips:['MUSIC']},
  {s:44.0,e:46.0,title:'Wish',query:'I wish our hearts could come together',rows:['together is one','lil-bieber2h','share'],chips:['LYRICS']},
  {s:46.0,e:48.0,title:'Eenie Meenie',query:'',rows:['Meenie Meenie Mo','by Sean Kingston','recommended'],chips:['MUSIC']},
  {s:48.0,e:50.0,title:'Messages',query:'Swipe up to turn on disappearing messages',rows:['Message:','Disappearing: ON','Message settings'],chips:['MESSAGE']},
  {s:50.0,e:52.0,title:'Messages',query:'',rows:['Lova','Disappearing messages','Settings'],chips:['MESSAGE']},
  {s:52.0,e:54.0,title:'Music',query:'',rows:['Shawty is a…','Eenie Meenie Mo','Share this story'],chips:['SHARE']},
  {s:54.0,e:56.2667,title:'Ask ChatGPT',query:'Create an image from this idea…',rows:['The Kid LAROI · Justin Bieber','dark UI · cinematic · vertical','Creating image'],chips:['Ask ChatGPT']},
];

const ease=Easing.out(Easing.quad);
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));

function stateFor(time){
 let idx=states.findIndex(x=>time>=x.s && time<x.e); return idx<0?states.length-1:idx;
}

function MobileState({state,small=false}){
 const frame=useCurrentFrame(); const local=frame/useVideoConfig().fps-state.s;
 const intro=interpolate(local,[0,.22],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:ease});
 const font=small?10:14, titleSize=small?15:22;
 return <div style={{position:'absolute',inset:0,background:C.surface3,color:C.text,fontFamily:'Arial,Helvetica,sans-serif',opacity:intro,transform:`translateY(${(1-intro)*8}px)`,overflow:'hidden'}}>
   <div style={{position:'absolute',left:12,top:10,right:12,height:30,display:'flex',alignItems:'center',gap:8}}>
     <div style={{fontSize:titleSize,fontWeight:800,flex:1}}>{state.title}</div>
     <div style={{fontSize:small?8:10,color:C.muted}}>⌁</div>
   </div>
   {state.query && <div style={{position:'absolute',left:12,top:48,right:12,height:34,border:`1px solid ${C.line}`,borderRadius:17,display:'flex',alignItems:'center',padding:'0 12px',fontSize:font,color:C.muted,background:'#0e130f'}}>{state.query}</div>}
   {state.chips?.length>0 && <div style={{position:'absolute',left:12,right:12,top:state.query?90:50,height:24,display:'flex',gap:6,overflow:'hidden'}}>{state.chips.map((c,i)=><div key={c+i} style={{border:`1px solid ${i===0?C.green:C.line}`,borderRadius:12,padding:'4px 8px',fontSize:small?7:9,color:i===0?C.green:C.muted,background:'#0d130e'}}>{c}</div>)}</div>}
   <div style={{position:'absolute',left:12,right:12,bottom:12,top:state.query||state.chips?.length?122:78,display:'flex',flexDirection:'column',gap:7}}>
     {state.rows.map((row,i)=><div key={row+i} style={{minHeight:small?25:34,borderBottom:`1px solid ${C.line}`,display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:font,color:i===0?C.text:C.muted}}><span>{row}</span><span style={{color:i===0?C.green:C.muted,fontSize:small?8:11}}>{i===0?'›':''}</span></div>)}
   </div>
 </div>;
}

function AppShell({state,small=false}){
 return <div style={{position:'absolute',left:small?74:26,top:small?52:88,width:small?336:524,height:small?250:320,borderRadius:small?18:20,background:'#0a0f0b',border:`1px solid ${C.line}`,overflow:'hidden',boxShadow:'0 18px 55px rgba(0,0,0,.35)'}}><MobileState state={state} small={small}/></div>;
}

export const WireframeVideo=()=>{
 const frame=useCurrentFrame(); const {fps}=useVideoConfig(); const time=frame/fps; const idx=stateFor(time); const state=states[idx];
 return <AbsoluteFill style={{background:C.bg,fontFamily:'Arial,Helvetica,sans-serif'}}>
  <Audio src={staticFile('audio/original_score.wav')} volume={0.48}/>
  <div style={{position:'absolute',left:0,top:0,right:0,bottom:0,background:'radial-gradient(circle at 50% 25%,rgba(90,130,80,.10),transparent 42%)'}}/>
  <div style={{position:'absolute',left:12,top:8,right:12,bottom:8,borderRadius:28,background:C.surface,border:`1px solid ${C.line}`,boxShadow:'0 25px 80px rgba(0,0,0,.38)',overflow:'hidden'}}>
    <div style={{position:'absolute',left:0,top:0,right:0,height:64,borderBottom:`1px solid ${C.line}`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:24,fontWeight:800,color:C.text}}>Wireframe</div>
    <div style={{position:'absolute',left:18,top:76,right:18,height:336,borderRadius:18,background:'#0a0f0b',border:`1px solid ${C.line}`,overflow:'hidden'}}>
      <div style={{position:'absolute',left:0,top:0,right:0,height:32,borderBottom:`1px solid ${C.line}`,padding:'9px 12px',fontSize:9,color:C.muted}}>Preview</div>
      <AppShell state={state} small/>
      <div style={{position:'absolute',left:12,bottom:10,fontSize:8,color:C.muted}}>wireframe preview</div><div style={{position:'absolute',right:12,bottom:10,fontSize:8,color:C.green}}>LIVE</div>
    </div>
    <div style={{position:'absolute',left:18,top:418,right:18,height:50,display:'flex',alignItems:'center',justifyContent:'space-between',color:C.muted,fontSize:12}}>
      <span>Half</span><span style={{color:C.text}}>100</span><span style={{fontVariantNumeric:'tabular-nums'}}>{`0:00:${String(Math.floor(time)).padStart(2,'0')}:${String(frame%30).padStart(2,'0')}`}</span>
      <div style={{position:'absolute',left:42,right:42,bottom:2,height:2,background:'#273328'}}><div style={{height:2,width:`${clamp(time/56.2667*100,0,100)}%`,background:C.green}}/></div>
    </div>
    <div style={{position:'absolute',top:476,left:0,right:0,textAlign:'center',fontSize:24,fontWeight:800}}>Result</div>
    <div style={{position:'absolute',left:18,top:520,right:18,bottom:22,borderRadius:18,background:'#0a0f0b',border:`1px solid ${C.line}`,overflow:'hidden'}}>
      <div style={{position:'absolute',left:0,top:0,right:0,height:32,borderBottom:`1px solid ${C.line}`,padding:'9px 12px',fontSize:9,color:C.muted}}>{state.title} · Result</div>
      <AppShell state={state}/>
      <div style={{position:'absolute',left:12,right:12,bottom:10,display:'flex',justifyContent:'space-between',fontSize:8,color:C.muted}}><span>workflow applied</span><span style={{color:C.green}}>ready</span></div>
    </div>
  </div>
 </AbsoluteFill>;
};
