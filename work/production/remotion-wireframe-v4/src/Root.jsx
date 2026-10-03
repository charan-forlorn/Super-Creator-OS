import React from 'react';
import {Composition} from 'remotion';
import {WireframeVideo} from './Video.jsx';
import {PremiumSingleScreen} from './PremiumSingleScreen.jsx';

export const RemotionRoot = () => (
  <>
    <Composition id="WireframeAutomation" component={WireframeVideo} durationInFrames={1688} fps={30} width={576} height={922} />
    <Composition
      id="PremiumSingleScreen"
      component={PremiumSingleScreen}
      durationInFrames={900}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(1, Math.ceil(Number(props?.duration_s || 30) * Number(props?.fps || 30))),
        fps: Number(props?.fps || 30),
        width: Number(props?.width || 1080),
        height: Number(props?.height || 1920),
      })}
      defaultProps={{states: undefined, captions: [], musicSrc: undefined, sfx: [], production_graph: undefined, fps: 30, width: 1080, height: 1920}}
    />
  </>
);
