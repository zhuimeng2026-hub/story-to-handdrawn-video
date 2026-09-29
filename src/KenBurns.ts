import type {CSSProperties} from 'react';
import {interpolate} from 'remotion';
import {smoothstep} from './easing';

// Ken Burns drift: a slow push-in with a small lateral move. The direction
// alternates by seed so a sequence does not drift one way all the way through,
// which reads as a slideshow rather than a film.
const ZOOM_END = 1.09;
const DRIFT_PERCENT = 1.5;

// The illustration is drawn slightly larger than its box and centred, so the
// drift always has painted pixels underneath it. Without this over-scan a
// translate of even 1% exposes an unpainted edge on the white page.
export const OVERSCAN = 1.06;

export type KenBurnsMotion = {
  scaleFrom: number;
  scaleTo: number;
  xFrom: number;
  xTo: number;
  yFrom: number;
  yTo: number;
};

export const motionFor = (seed: string): KenBurnsMotion => {
  const n = [...seed].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const rightward = n % 2 === 0;
  return {
    scaleFrom: 1.0,
    scaleTo: ZOOM_END,
    xFrom: rightward ? -DRIFT_PERCENT : DRIFT_PERCENT,
    xTo: rightward ? DRIFT_PERCENT : -DRIFT_PERCENT,
    yFrom: 1.0,
    yTo: -1.0,
  };
};

export const overscanStyle = (): CSSProperties => ({
  position: 'absolute',
  top: `${(1 - OVERSCAN) * 50}%`,
  left: `${(1 - OVERSCAN) * 50}%`,
  width: `${OVERSCAN * 100}%`,
  height: `${OVERSCAN * 100}%`,
  transformOrigin: 'center center',
});

// `progress` runs 0..1 across the scene. Easing keeps the motion from starting
// and stopping abruptly at each cut.
export const kenBurnsStyle = (
  progress: number,
  motion: KenBurnsMotion,
): CSSProperties => {
  const t = smoothstep(Math.min(1, Math.max(0, progress)));
  return {
    transform: `translate(${interpolate(t, [0, 1], [motion.xFrom, motion.xTo])}%, ` +
      `${interpolate(t, [0, 1], [motion.yFrom, motion.yTo])}%) ` +
      `scale(${interpolate(t, [0, 1], [motion.scaleFrom, motion.scaleTo])})`,
  };
};
