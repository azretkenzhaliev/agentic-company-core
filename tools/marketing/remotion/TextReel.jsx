// A 9:16 kinetic-text reel: one line at a time, in the vetted fonts.
// Props: { lines: [{ text, seconds }], background, foreground, accent }.
import '@fontsource/golos-text/700.css';
import '@fontsource/montserrat/800.css';
import { useEffect, useState } from 'react';
import { AbsoluteFill, continueRender, delayRender, interpolate, Sequence, useCurrentFrame } from 'remotion';

export const textReelFrames = (props, fps) => Math.max(1, Math.round(props.lines.reduce((s, l) => s + l.seconds, 0) * fps));

const Line = ({ text, frames, color }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8, frames - 8, frames], [0, 1, 1, 0], { extrapolateRight: 'clamp' });
  const y = interpolate(frame, [0, 10], [40, 0], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ justifyContent: 'center', padding: '250px 88px 340px' }}>
      <div style={{ font: "800 96px/1.08 'Montserrat', sans-serif", color, opacity, transform: `translateY(${y}px)` }}>{text}</div>
    </AbsoluteFill>
  );
};

export const TextReel = ({ lines, background, foreground, accent }) => {
  const [handle] = useState(() => delayRender('vetted fonts'));
  useEffect(() => {
    const text = `Aa ${lines.map((line) => line.text).join(' ')}`;
    Promise.all([
      document.fonts.load("800 96px 'Montserrat'", text),
      document.fonts.load("700 48px 'Golos Text'", text),
    ]).then(() => continueRender(handle));
  }, [handle]);
  const fps = 30;
  let from = 0;
  return (
    <AbsoluteFill style={{ background }}>
      <div style={{ position: 'absolute', left: 88, top: 250, width: 120, height: 12, background: accent }} />
      {lines.map((line, i) => {
        const frames = Math.round(line.seconds * fps);
        const seq = (
          <Sequence key={i} from={from} durationInFrames={frames}>
            <Line text={line.text} frames={frames} color={foreground} />
          </Sequence>
        );
        from += frames;
        return seq;
      })}
    </AbsoluteFill>
  );
};
