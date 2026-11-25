// Remotion entry: compositions for reels that need no filming.
import { Composition, registerRoot } from 'remotion';
import { Captions, vetFont } from './Captions.jsx';
import { captionFrames } from './captionCards.mjs';
import { TextReel, textReelFrames } from './TextReel.jsx';

const FPS = 30;
const example = {
  lines: [
    { text: 'A new AI model is out', seconds: 2 },
    { text: 'Was das neue Modell bedeutet', seconds: 2.5 },
  ],
  background: '#0f1014',
  foreground: '#f4f2ec',
  accent: '#7cf29c',
};
const exampleWords = {
  words: [
    { text: 'New', start: 0, end: 0.4 },
    { text: 'AI', start: 0.4, end: 0.7 },
    { text: 'model', start: 0.7, end: 1.2 },
    { text: 'out', start: 1.2, end: 1.7 },
  ],
};

const Root = () => (
  <>
    <Composition
      id="TextReel"
      component={TextReel}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={textReelFrames(example, FPS)}
      defaultProps={example}
      calculateMetadata={({ props }) => ({ durationInFrames: textReelFrames(props, FPS) })}
    />
    <Composition
      id="Captions"
      component={Captions}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={captionFrames(exampleWords.words, FPS)}
      defaultProps={exampleWords}
      calculateMetadata={({ props }) => {
        vetFont(props.font);
        return { durationInFrames: captionFrames(props.words, FPS) };
      }}
    />
  </>
);

registerRoot(Root);
