// Caption cards from word timings: which words share a card, when it shows, which word is being said.
// No JSX and no browser, so `node --test` can run it. The numbers are knowledge/marketing/craft-standard.md's.
const MIN_WORDS = 3;
const MAX_WORDS = 5;
const MAX_SECONDS = 2;
const MAX_CHARS = 42;
const GAP = 0.7; // a longer silence ends the phrase: a card never sits through a pause
const HOLD = 0.3; // a card stays this long after its last word, unless the next one takes over
const SENTENCE_END = /[.?!…]$/;

export const captionSize = (height) => Math.round(height * 0.075);

function phrases(words) {
  const found = [];
  for (const word of words) {
    const phrase = found.at(-1);
    if (phrase && word.start - phrase.at(-1).end <= GAP) phrase.push(word);
    else found.push([word]);
  }
  return found;
}

function endsCard(card, next) {
  if (card.length === MAX_WORDS) return true;
  if (card.length < MIN_WORDS) return false;
  const text = [...card, next].map((word) => word.text).join(' ');
  return SENTENCE_END.test(card.at(-1).text) || next.end - card[0].start > MAX_SECONDS || text.length > MAX_CHARS;
}

// Only a phrase of one or two words makes a card under MIN_WORDS: a short last card joins or borrows from the one before.
function phraseCards(phrase) {
  const cards = [[]];
  for (const word of phrase) {
    if (cards.at(-1).length && endsCard(cards.at(-1), word)) cards.push([]);
    cards.at(-1).push(word);
  }
  const [previous, last] = cards.slice(-2);
  if (!last || last.length >= MIN_WORDS) return cards;
  if (previous.length + last.length <= MAX_WORDS) cards.splice(-2, 2, [...previous, ...last]);
  else last.unshift(...previous.splice(last.length - MIN_WORDS));
  return cards;
}

export const captionCards = (words) => phrases(words).flatMap(phraseCards);

export function cardAt(cards, seconds) {
  const card = cards.findLast((candidate) => candidate[0].start <= seconds);
  return card && seconds < card.at(-1).end + HOLD ? card : null;
}

export const activeWord = (card, seconds) => card.findLast((word) => word.start <= seconds);

export const captionFrames = (words, fps) => Math.ceil(((words.at(-1)?.end ?? 0) + HOLD) * fps);
