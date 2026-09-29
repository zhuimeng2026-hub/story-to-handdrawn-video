import type {CSSProperties} from 'react';
import {Img, staticFile, useCurrentFrame} from 'remotion';
import {revealProgress} from './easing';

type LayerWipeProps = {
  src: string;
  startFrame: number;
  durationFrames: number;
  opacity?: number;
  zIndex: number;
  treatment?: 'bw' | 'detail' | 'color';
  // Ken Burns drift, shared by every plate in a scene so the composite moves as
  // one image. Omitted for plates that must stay pinned (uploaded masters).
  motionStyle?: CSSProperties;
  overscanStyle?: CSSProperties;
};

const treatmentFilter = {
  bw: 'grayscale(1) contrast(1.72) brightness(1.12)',
  detail: 'grayscale(1) contrast(1.28) brightness(1.055)',
  color: 'brightness(1.035) contrast(1.04)',
} as const;

export const LayerWipe: React.FC<LayerWipeProps> = ({
  src,
  startFrame,
  durationFrames,
  opacity = 1,
  zIndex,
  treatment = 'color',
  motionStyle,
  overscanStyle,
}) => {
  const frame = useCurrentFrame();
  const progress = revealProgress(frame, startFrame, durationFrames);
  // Product rule: every drawing plate is revealed left-to-right. Keeping one
  // mask direction across bw/detail/color prevents the composition from
  // appearing to jump when a new plate takes over.
  const clipPath = `inset(0 ${100 - progress * 100}% 0 0)`;

  return (
    <div
      style={{
        position: 'absolute',
        zIndex,
        left: 74,
        right: 74,
        top: 382,
        // The bottom edge leaves room for the burned-in subtitle so translated
        // text can never sit on top of the drawing.
        bottom: 232,
        clipPath,
        opacity,
        overflow: 'hidden',
      }}
    >
      <div style={{...overscanStyle, ...motionStyle}}>
        <Img
          src={staticFile(src)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            objectPosition: 'center center',
            filter: treatmentFilter[treatment],
          }}
        />
      </div>
    </div>
  );
};
