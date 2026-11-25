// Captions on a transparent background, for a reel's overlay list: 3-5 words a card, the word being said in one colour
// (reel-script §3). Props: { words: [{ text, start, end }], font, size, bottom, color, activeColor, strokeWidth, strokeColor }.
// `words` is voice/scribe.py's <name>.words.json, in seconds. `size` defaults to 7.5% of the height, and shrinks for a word
// too wide for the line. `bottom` is the card's distance from the frame's bottom edge; it grows upward from there.
// `strokeWidth` is what shows outside the letter: the fill covers the inner half of the stroke.
import '@fontsource/golos-text/700.css';
import '@fontsource/montserrat/800.css';
import { useEffect, useMemo, useState } from 'react';
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig } from 'remotion';
import { activeWord, captionCards, captionSize, cardAt } from './captionCards.mjs';

const WEIGHTS = { Montserrat: 800, 'Golos Text': 700 };
const FONT = 'Golos Text';
const SIDE = 88;

// Throws for a font that isn't vetted. The composition's calculateMetadata calls it too, so the render fails before any page
// opens: Remotion 4.0.535 hears a page's errors only while it renders a frame, and a throw as the component mounts often
// comes before that. The render then passes with empty frames.
export const vetFont = (font = FONT) => {
  if (!(font in WEIGHTS)) throw new Error(`Captions: the font must be ${Object.keys(WEIGHTS).join(' or ')}, not ${font}`);
};

function fittedSize(card, font, size, room) {
  const context = document.createElement('canvas').getContext('2d');
  context.font = `${WEIGHTS[font]} ${size}px '${font}'`;
  const widest = Math.max(...card.map((word) => context.measureText(word.text).width));
  return Math.min(size, (size * room) / widest);
}

export const Captions = ({ words, font = FONT, size, bottom = 340, color = '#ffffff', activeColor = '#ffd400',
  strokeWidth = 4, strokeColor = '#000000' }) => {
  vetFont(font);
  const { fps, height, width } = useVideoConfig();
  const px = size ?? captionSize(height);
  const cards = useMemo(() => captionCards(words), [words]);
  const [handle] = useState(() => delayRender('vetted fonts'));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const text = `Aa ${words.map((word) => word.text).join(' ')}`;
    document.fonts.load(`${WEIGHTS[font]} ${px}px '${font}'`, text)
      .then((faces) => {
        if (!faces.length) throw new Error(`Captions: ${font} didn't load`);
        setReady(true);
      })
      .catch(cancelRender);
  }, [font, px, words]);
  useEffect(() => {
    if (ready) continueRender(handle);
  }, [ready, handle]);

  const seconds = useCurrentFrame() / fps;
  const card = ready ? cardAt(cards, seconds) : null;
  if (!card) return <AbsoluteFill />;
  const active = activeWord(card, seconds);
  const fitted = fittedSize(card, font, px, width - 2 * SIDE - 2 * strokeWidth);
  return (
    <AbsoluteFill>
      <div style={{ position: 'absolute', left: SIDE, right: SIDE, bottom, paddingBottom: '0.1em', textAlign: 'center', color,
        font: `${WEIGHTS[font]} ${fitted}px/1.1 '${font}', sans-serif`,
        WebkitTextStroke: `${2 * strokeWidth}px ${strokeColor}`, paintOrder: 'stroke fill' }}>
        {card.map((word, index) => (
          <span key={index} style={word === active ? { color: activeColor } : undefined}>{word.text} </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};
