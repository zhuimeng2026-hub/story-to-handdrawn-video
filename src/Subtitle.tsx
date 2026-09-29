import type {CSSProperties} from 'react';
import {useCurrentFrame} from 'remotion';
import {revealProgress} from './easing';

type SubtitleProps = {
  text?: string | null;
  startFrame: number;
  durationFrames: number;
  fps: number;
};

const FADE_FRAMES_RATIO = 0.22;

const subtitleStyle = (): CSSProperties => ({
  fontFamily:
    'OriginalDiaryHand, "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  fontSize: 38,
  fontWeight: 400,
  lineHeight: 1.52,
  letterSpacing: '0.012em',
  color: '#3d3d38',
  margin: 0,
  textAlign: 'left',
});

// Fades in slightly after the poem line lands and out just before the scene
// turns over, so the two text blocks never compete for attention at once.
export const Subtitle: React.FC<SubtitleProps> = ({
  text,
  startFrame,
  durationFrames,
  fps,
}) => {
  const frame = useCurrentFrame();
  if (!text) return null;

  const fade = Math.max(2, Math.round(durationFrames * FADE_FRAMES_RATIO));
  const inStart = startFrame + fade;
  const outStart = durationFrames - fade;
  const appear = revealProgress(frame, inStart, fade);
  const vanish = 1 - revealProgress(frame, outStart, fade);
  const opacity = Math.min(appear, vanish);

  if (opacity <= 0.01) return null;

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 45,
        left: 104,
        right: 96,
        bottom: 74,
        opacity,
        transform: `translateY(${(1 - appear) * 6}px)`,
      }}
    >
      <p style={subtitleStyle()}>{text}</p>
    </div>
  );
};
