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

function withAlpha(color, alpha, fallback) {
  if (typeof color === 'string' && /^#[0-9a-fA-F]{6}$/.test(color)) return color + alpha;
  return color || fallback;
}

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

function CaptionOverlay({captions, accent, textColor, fontFamily}) {
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
        fontFamily: fontFamily || 'Tahoma, Arial, sans-serif', fontSize: 54, lineHeight: 1.13,
        fontWeight: 800, color: textColor || COLORS.text,
      }}>
        {page.tokens.map((token, idx) => (
          <span key={idx} style={{color: idx <= active ? (accent || COLORS.accent) : (textColor || COLORS.text)}}>
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
  const brandText = brand?.colors?.neutrals?.[0] || brand?.colors?.primary || COLORS.text;
  const brandMuted = brand?.colors?.neutrals?.[1] || COLORS.muted;
  const brandShell = brand?.colors?.primary || COLORS.bg;
  const brandPanel = brand?.colors?.secondary || COLORS.panel;
  const brandLine = brand?.colors?.neutrals?.[2] || COLORS.line;
  const brandAccentStroke = withAlpha(brandAccent, '55', brandAccent);
  const brandLineStroke = withAlpha(brandLine, '55', brandLine);
  const brandAccentGlow = withAlpha(brandAccent, '14', 'rgba(122,190,120,.13)');
  const brandName = brand?.name || 'RESULT';
  const brandCta = brand?.cta?.label || '';

  return (
    <AbsoluteFill style={{background: brandShell, color: brandText, fontFamily: bodyFont, overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 22%, ' + brandAccentGlow + ', transparent 34%)'}}/>
      <div style={{
        position: 'absolute', inset: 24, borderRadius: 42,
        background: brandShell,
        border: '1px solid ' + brandLineStroke, boxShadow: '0 28px 90px rgba(0,0,0,.42)',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 118,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 46px', borderBottom: '1px solid ' + brandLineStroke,
        }}>
          <div style={{fontSize: 26, color: brandMuted, letterSpacing: 1}}>{brandName}</div>
          <div style={{
            padding: '8px 14px', borderRadius: 16,
            border: '1px solid ' + brandAccentStroke, color: brandAccent,
            fontSize: 16, fontWeight: 800,
          }}>LIVE</div>
        </div>

        <div style={{
          position: 'absolute', left: 46, right: 46, top: 156, bottom: 270,
          borderRadius: 34, background: brandPanel,
          border: '1px solid ' + brandLineStroke, boxShadow: '0 14px 45px rgba(0,0,0,.22)',
          padding: 34,
        }}>
          <div style={{
            opacity: enter,
            transform: 'translateY(' + ((1 - enter) * 18) + 'px) scale(' + (0.985 + enter * 0.015) + ')',
            height: '100%', display: 'flex', flexDirection: 'column',
          }}>
            <div style={{fontSize: 18, color: brandAccent, fontWeight: 800, letterSpacing: 1.2}}>
              <span style={{color: brandAccent}}>{state.eyebrow}</span>
            </div>
            <div style={{marginTop: 14, fontSize: 56, lineHeight: 1.03, fontWeight: 900, letterSpacing: -1.4, fontFamily: headingFont}}>
              {state.headline}
            </div>
            <div style={{marginTop: 18, maxWidth: 780, fontSize: 24, lineHeight: 1.45, color: brandMuted, fontFamily: bodyFont}}>
              {state.body}
            </div>

            <div style={{display: 'flex', gap: 10, marginTop: 28}}>
              {(state.tags || []).map((tag) => (
                <div key={tag} style={{
                  padding: '8px 14px', borderRadius: 18,
                  background: brandShell,
                  border: '1px solid ' + brandAccentStroke,
                  color: brandAccent, fontSize: 14, fontWeight: 800,
                }}>{tag}</div>
              ))}
            </div>

            <div style={{marginTop: 'auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16}}>
              {[['01', 'Clarity', 'The hierarchy is obvious.'], ['02', 'Motion', 'Transitions have a reason.']].map(([n, t, d]) => (
                <div key={n} style={{
                  padding: 20, borderRadius: 22, background: brandShell,
                  border: '1px solid ' + brandLineStroke,
                }}>
                  <div style={{fontSize: 14, color: brandMuted}}>{n}</div>
                  <div style={{marginTop: 5, fontSize: 22, fontWeight: 800}}>{t}</div>
                  <div style={{marginTop: 4, fontSize: 15, lineHeight: 1.4, color: brandMuted}}>{d}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{position: 'absolute', left: 46, right: 46, bottom: 112, display: 'flex', alignItems: 'center', gap: 16}}>
          <div style={{fontSize: 16, color: brandMuted}}>0:{String(Math.floor(time)).padStart(2, '0')}</div>
          <div style={{flex: 1, height: 5, borderRadius: 5, background: brandLine, overflow: 'hidden'}}>
            <div style={{height: '100%', width: (progress * 100) + '%', background: brandAccent}}/>
          </div>
          <div style={{fontSize: 16, color: brandMuted}}>{String(state.title || 'Result').toUpperCase()}</div>
        </div>
      </div>

      <CaptionOverlay captions={captions} accent={brandAccent} textColor={brandText} fontFamily={bodyFont}/>

      {musicSrc ? <Audio src={staticFile(musicSrc)} volume={0.18} loop/> : null}
      {(sfx || []).map((fx) => (
        <Sequence key={fx.src + '-' + fx.startFrame} from={fx.startFrame || 0} layout="none">
          <Audio src={staticFile(fx.src)} volume={fx.volume || 0.28}/>
        </Sequence>
      ))}

      <div style={{position: 'absolute', left: 46, right: 46, bottom: 104, display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: brandMuted, fontSize: 12, letterSpacing: 1.4}}>
        <div>{brandName} · {stateIndex + 1}/{states.length}</div>
        {brandCta ? (
          <div style={{padding: '8px 14px', borderRadius: 16, border: '1px solid ' + brandAccentStroke, color: brandAccent, fontWeight: 800}}>
            {brandCta}
          </div>
        ) : (
          <div>SINGLE SCREEN PRODUCTION</div>
        )}
      </div>
    </AbsoluteFill>
  );
};
