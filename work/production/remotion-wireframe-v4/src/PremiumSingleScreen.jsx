import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions} from '@remotion/captions';

const COLORS = {
  bg: '#07100a',
  panel: '#0b140d',
  panel2: '#0f1b11',
  text: '#f5f7f3',
  muted: '#829184',
  accent: '#b7ef83',
  line: '#26362a',
};

const DEFAULT_STATES = [
  {start: 0, end: 3, title: 'Today', eyebrow: 'Focus', headline: 'Make the next step obvious.', body: 'One clear action beats ten open tabs.', tags: ['FOCUS', 'TODAY'], accent: '#b7ef83'},
  {start: 3, end: 7, title: 'Inbox', eyebrow: 'Automation', headline: 'Your workflow is ready.', body: 'Review, approve, and let the system execute.', tags: ['READY', 'AUTOMATION'], accent: '#8de7aa'},
  {start: 7, end: 11, title: 'Music', eyebrow: 'Now playing', headline: 'A calmer pace. A sharper result.', body: 'Use sound to reinforce the cut, not fight it.', tags: ['AUDIO', 'MIX'], accent: '#84d9ff'},
  {start: 11, end: 15, title: 'Result', eyebrow: 'Preview', headline: 'The screen stays simple.', body: 'Motion, hierarchy and captions do the heavy lifting.', tags: ['UI', 'CAPTION'], accent: '#f0c97d'},
];

function currentState(states, time) {
  if (!states || !states.length) return DEFAULT_STATES[0];
  return states.find((s) => time >= s.start && time < s.end) || states[states.length - 1];
}

function CaptionOverlay({captions, accent}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!captions || !captions.length) return null;
  const pages = useMemo(
    () => createTikTokStyleCaptions({
      captions,
      combineTokensWithinMilliseconds: 160,
      breakOnSilenceAfterMilliseconds: 550,
    }).pages,
    [captions],
  );
  const ms = (frame / fps) * 1000;
  const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);
  if (!page) return null;
  const active = page.tokens.findIndex((t) => ms >= t.fromMs && ms < t.toMs);
  return (
    <div style={{position: 'absolute', left: 78, right: 78, bottom: 172, display: 'flex', justifyContent: 'center'}}>
      <div style={{
        maxWidth: 900, padding: '18px 26px', borderRadius: 24,
        background: 'rgba(3,8,4,.86)', border: '1px solid rgba(255,255,255,.10)',
        boxShadow: '0 18px 50px rgba(0,0,0,.30)', textAlign: 'center',
        fontFamily: 'Tahoma, Arial, sans-serif', fontSize: 54, lineHeight: 1.13,
        fontWeight: 800, color: COLORS.text,
      }}>
        {page.tokens.map((token, idx) => (
          <span key={idx} style={{color: idx <= active ? (accent || COLORS.accent) : COLORS.text}}>
            {token.text}{' '}
          </span>
        ))}
      </div>
    </div>
  );
}

export const PremiumSingleScreen = ({states = DEFAULT_STATES, captions = [], musicSrc, sfx = [], brand}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const time = frame / fps;
  const state = currentState(states, time);
  const stateIndex = Math.max(0, states.findIndex((s) => s.start === state.start));
  const local = Math.max(0, time - state.start);
  const enter = interpolate(local, [0, 0.35], [0, 1], {extrapolateRight: 'clamp'});
  const progress = interpolate(time, [0, durationInFrames / fps], [0, 1], {extrapolateRight: 'clamp'});
  const brandAccent = brand?.colors?.accent || state.accent || COLORS.accent;
  const headingFont = brand?.fonts?.heading || 'Tahoma, Arial, sans-serif';
  const bodyFont = brand?.fonts?.body || 'Tahoma, Arial, sans-serif';
  const brandText = brand?.colors?.primary || COLORS.text;

  return (
    <AbsoluteFill style={{background: COLORS.bg, color: brandText, fontFamily: bodyFont, overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 22%, rgba(122,190,120,.13), transparent 34%)'}}/>
      <div style={{
        position: 'absolute', inset: 24, borderRadius: 42,
        background: 'linear-gradient(160deg, #0c170e, #07100a 62%, #09130b)',
        border: '1px solid rgba(255,255,255,.07)', boxShadow: '0 28px 90px rgba(0,0,0,.42)',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 118,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 46px', borderBottom: '1px solid rgba(255,255,255,.06)',
        }}>
          <div style={{fontSize: 26, color: COLORS.muted, letterSpacing: 1}}>RESULT</div>
          <div style={{
            padding: '8px 14px', borderRadius: 16,
            border: '1px solid rgba(183,239,131,.30)', color: COLORS.accent,
            fontSize: 16, fontWeight: 800,
          }}>LIVE</div>
        </div>

        <div style={{
          position: 'absolute', left: 46, right: 46, top: 156, bottom: 270,
          borderRadius: 34, background: COLORS.panel,
          border: '1px solid rgba(255,255,255,.06)', boxShadow: '0 14px 45px rgba(0,0,0,.22)',
          padding: 34,
        }}>
          <div style={{
            opacity: enter,
            transform: 'translateY(' + ((1 - enter) * 18) + 'px) scale(' + (0.985 + enter * 0.015) + ')',
            height: '100%', display: 'flex', flexDirection: 'column',
          }}>
            <div style={{fontSize: 18, color: state.accent || COLORS.accent, fontWeight: 800, letterSpacing: 1.2}}>
              <span style={{color: brandAccent}}>{state.eyebrow}</span>
            </div>
            <div style={{marginTop: 14, fontSize: 56, lineHeight: 1.03, fontWeight: 900, letterSpacing: -1.4, fontFamily: headingFont}}>
              {state.headline}
            </div>
            <div style={{marginTop: 18, maxWidth: 780, fontSize: 24, lineHeight: 1.45, color: COLORS.muted, fontFamily: bodyFont}}>
              {state.body}
            </div>

            <div style={{display: 'flex', gap: 10, marginTop: 28}}>
              {(state.tags || []).map((tag) => (
                <div key={tag} style={{
                  padding: '8px 14px', borderRadius: 18,
                  background: COLORS.panel2,
                  border: '1px solid ' + (state.accent || COLORS.line) + '38',
                  color: brandAccent, fontSize: 14, fontWeight: 800,
                }}>{tag}</div>
              ))}
            </div>

            <div style={{marginTop: 'auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16}}>
              {[['01', 'Clarity', 'The hierarchy is obvious.'], ['02', 'Motion', 'Transitions have a reason.']].map(([n, t, d]) => (
                <div key={n} style={{
                  padding: 20, borderRadius: 22, background: '#0d180f',
                  border: '1px solid rgba(255,255,255,.05)',
                }}>
                  <div style={{fontSize: 14, color: COLORS.muted}}>{n}</div>
                  <div style={{marginTop: 5, fontSize: 22, fontWeight: 800}}>{t}</div>
                  <div style={{marginTop: 4, fontSize: 15, lineHeight: 1.4, color: COLORS.muted}}>{d}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{position: 'absolute', left: 46, right: 46, bottom: 112, display: 'flex', alignItems: 'center', gap: 16}}>
          <div style={{fontSize: 16, color: COLORS.muted}}>0:{String(Math.floor(time)).padStart(2, '0')}</div>
          <div style={{flex: 1, height: 5, borderRadius: 5, background: '#1b281e', overflow: 'hidden'}}>
            <div style={{height: '100%', width: (progress * 100) + '%', background: state.accent || COLORS.accent}}/>
          </div>
          <div style={{fontSize: 16, color: COLORS.muted}}>{String(state.title || 'Result').toUpperCase()}</div>
        </div>
      </div>

      <CaptionOverlay captions={captions}/>

      {musicSrc ? <Audio src={staticFile(musicSrc)} volume={0.18} loop/> : null}
      {(sfx || []).map((fx) => (
        <Sequence key={fx.src + '-' + fx.startFrame} from={fx.startFrame || 0} layout="none">
          <Audio src={staticFile(fx.src)} volume={fx.volume || 0.28}/>
        </Sequence>
      ))}

      <div style={{position: 'absolute', left: 46, right: 46, bottom: 36, textAlign: 'center', color: 'rgba(255,255,255,.34)', fontSize: 12, letterSpacing: 2}}>
        {stateIndex + 1}/{states.length} · SINGLE SCREEN PRODUCTION
      </div>
    </AbsoluteFill>
  );
};
