// Tests for the Captions component: the card rules, then one real render through Remotion, laid over a reel by
// video/compile.mjs. Rendered with Playwright's Chromium, so the test downloads nothing.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test, { after } from 'node:test';
import { RenderInternals } from '@remotion/renderer';
import ffmpeg from 'ffmpeg-static';
import { chromium } from 'playwright';
import { activeWord, captionCards, captionFrames, captionSize, cardAt } from '../remotion/captionCards.mjs';
import { readProps, renderReel } from '../render/reel.mjs';
import { compile } from '../video/compile.mjs';

const word = (text, start, end = start + 0.2) => ({ text, start, end });
const steady = (texts, step = 0.3) => texts.map((text, i) => word(text, i * step, (i + 1) * step));
const numbered = (count, step) => steady(Array.from({ length: count }, (_, i) => `w${i}`), step);
const sizes = (words) => captionCards(words).map((card) => card.length);

test('every card holds 3 to 5 words, the last one too, and no word is lost', () => {
  for (let count = 3; count <= 24; count += 1) {
    const words = numbered(count);
    const cards = captionCards(words);
    assert.ok(cards.every((card) => card.length >= 3 && card.length <= 5), `${count} words: ${cards.map((c) => c.length)}`);
    assert.deepEqual(cards.flat(), words);
  }
});

test('the last card joins the one before when they fit, or borrows from it', () => {
  assert.deepEqual(sizes(numbered(6)), [3, 3]);
  assert.deepEqual(sizes(numbered(7)), [4, 3]);
  assert.deepEqual(sizes(numbered(5)), [5]);
});

test('a sentence end closes a card of 3 or more, not a shorter one', () => {
  assert.deepEqual(sizes(steady(['one', 'two', 'three.', 'four', 'five', 'six'])), [3, 3]);
  assert.deepEqual(sizes(steady(['one', 'two.', 'three', 'four'])), [4]);
});

test('a card of 3 or more ends before it passes 2 seconds or 42 characters', () => {
  assert.deepEqual(sizes(numbered(6, 0.6)), [3, 3]);
  assert.deepEqual(sizes(steady(Array(6).fill('x'.repeat(10)))), [3, 3]);
});

test('a pause ends a phrase at any count, and only a phrase under 3 words makes a short card', () => {
  const words = [word('a', 0), word('b', 0.3), word('c', 2), word('d', 2.3), word('e', 2.6), word('f', 2.9)];
  assert.deepEqual(sizes(words), [2, 4]);
  assert.deepEqual(sizes([word('alone', 1)]), [1]);
  assert.deepEqual(sizes([]), []);
});

test('a card shows from its first word to a beat after its last, and doesn\'t sit through a pause', () => {
  const words = [word('a', 1, 1.2), word('b', 1.2, 1.4), word('c', 1.4, 1.6), word('d', 4, 4.2), word('e', 4.2, 4.4), word('f', 4.4, 4.6)];
  const cards = captionCards(words);
  assert.equal(cardAt(cards, 0.9), null);
  assert.equal(cardAt(cards, 1), cards[0]);
  assert.equal(cardAt(cards, 1.8), cards[0]);
  assert.equal(cardAt(cards, 2), null);
  assert.equal(cardAt(cards, 4), cards[1]);
  assert.equal(activeWord(cards[0], 1.3).text, 'b');
  assert.equal(activeWord(cards[0], 1.8).text, 'c');
});

test('the next card takes over at its first word, inside the last one\'s hold', () => {
  const cards = captionCards(numbered(6));
  assert.equal(cardAt(cards, cards[1][0].start), cards[1]);
});

test('the overlay lasts through the last card, and a default size is 7-8% of the height', () => {
  assert.equal(captionFrames([word('a', 0, 2)], 30), 69);
  assert.equal(captionFrames([], 30), 9);
  assert.equal(captionSize(1920), 144);
  assert.ok(captionSize(1920) / 1920 >= 0.07 && captionSize(1920) / 1920 <= 0.08);
});

const root = mkdtempSync(join(tmpdir(), 'mkt-captions-test-'));
after(() => rmSync(root, { recursive: true, force: true }));
const M = (p) => join('workspaces/marketing', p);
for (const d of ['inbox', 'media/b/w/p']) mkdirSync(join(root, M(d)), { recursive: true });

test('--words puts the word timings into the style props', () => {
  const style = join(root, 'style.json');
  const timings = join(root, 'take.words.json');
  writeFileSync(style, JSON.stringify({ font: 'Montserrat' }));
  writeFileSync(timings, JSON.stringify([word('neu', 0)]));
  assert.deepEqual(readProps(style, timings), { font: 'Montserrat', words: [word('neu', 0)] });
  assert.deepEqual(readProps(style), { font: 'Montserrat' });
});

const browser = { browserExecutable: chromium.executablePath(), chromeMode: 'chrome-for-testing' };
const render = (options) => renderReel({ ...options, composition: 'Captions', browser });
const WIDTH = 1080;
const HEIGHT = 1920;
const frameAt = (rel, seconds) => {
  const run = spawnSync(ffmpeg, ['-loglevel', 'error', '-ss', String(seconds), '-i', join(root, rel), '-frames:v', '1', '-f', 'rawvideo',
    '-pix_fmt', 'rgb24', '-'], { maxBuffer: 3 * WIDTH * HEIGHT * 2 });
  assert.equal(run.status, 0, String(run.stderr));
  return run.stdout;
};
// The box around the pixels `matches` picks, or null.
const box = (frame, matches) => {
  let found = null;
  for (let y = 0; y < HEIGHT; y += 1) {
    for (let x = 0; x < WIDTH; x += 1) {
      const at = 3 * (y * WIDTH + x);
      if (!matches(frame[at], frame[at + 1], frame[at + 2])) continue;
      found ??= { left: x, right: x, top: y, bottom: y };
      found = { left: Math.min(found.left, x), right: Math.max(found.right, x), top: found.top, bottom: y };
    }
  }
  return found;
};
const background = [30, 90, 160];
const ink = (r, g, b) => [r, g, b].some((value, i) => Math.abs(value - background[i]) > 40);
const active = (r, g, b) => r > 200 && g < 70 && b < 70;

test('the render is transparent, marks the word being said, keeps to the safe zone and survives compile.mjs', async () => {
  const words = [word('Heute', 0.4, 0.8), word('neue', 0.8, 1.2), word('Idee', 1.2, 1.6), word('Grundstücksverwalter', 1.6, 2.4), word('Änderungen', 2.4, 3), word('groß', 3, 3.2)];
  const overlay = M('media/b/w/p/captions.mov');
  await render({ props: { words, activeColor: '#ff0000' }, out: join(root, overlay) });

  const take = M('inbox/take.mp4');
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', `color=c=0x${background.map((v) => v.toString(16).padStart(2, '0')).join('')}:s=${WIDTH}x${HEIGHT}:d=4:r=30`,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', join(root, take)]);
  assert.equal(made.status, 0, String(made.stderr));
  const reel = M('media/b/w/p/reel.mp4');
  compile({ clips: [{ file: take, in: 0, out: 4 }], overlays: [{ file: overlay, start: 0 }] }, join(root, reel), { root });

  assert.equal(box(frameAt(reel, 0.1), ink), null, 'nothing shows before the first word');
  const first = frameAt(reel, 0.5);
  const second = frameAt(reel, 1);
  const inkBox = box(second, ink);
  assert.ok(inkBox, 'the card shows');
  assert.ok(inkBox.bottom < HEIGHT - 340, `the bottom 340 px stay clear: ${inkBox.bottom}`);
  assert.ok(box(first, active).right < box(second, active).left, 'the active colour moves to the next word');

  const long = box(frameAt(reel, 2), ink);
  assert.ok(long.left >= 88 && long.right < WIDTH - 88, `a long word keeps the side margins: ${long.left}-${long.right}`);
  assert.equal(box(frameAt(reel, 3.9), ink), null, 'nothing shows after the last card');
});

test('Montserrat renders as well, and a font that isn\'t vetted fails the render', async () => {
  const words = [word('äöü', 0, 0.3)];
  await render({ props: { words, font: 'Montserrat' }, out: join(root, M('media/b/w/p/montserrat.mov')) });
  assert.ok(box(frameAt(M('media/b/w/p/montserrat.mov'), 0.1), (r, g) => r > 200 && g > 180), 'the active word shows');
  await assert.rejects(
    render({ props: { words, font: 'Arial' }, out: join(root, M('media/b/w/p/arial.mov')) }),
    /the font must be Montserrat or Golos Text, not Arial/);
});

test('a render waits for a page\'s response when Chrome reports it after the page has loaded', async () => {
  // Holds back each page's Network.responseReceivedExtraInfo events until 100 ms after its document has loaded: the order a
  // busy Mac gives now and then.
  const proto = RenderInternals.HeadlessBrowser.prototype;
  const { newPage } = proto;
  let late = 0;
  proto.newPage = async function (options) {
    const page = await newPage.call(this, options);
    const client = page._client();
    const emit = client.emit.bind(client);
    let document = null;
    let held = [];
    client.emit = (type, event) => {
      if (type === 'Network.requestWillBeSent' && event.type === 'Document' && event.requestId === event.loaderId) document = event.requestId;
      if (type === 'Network.responseReceivedExtraInfo') {
        if (held) return held.push(event) > 0;
        if (event.requestId === document) late += 1;
      }
      const handled = emit(type, event);
      if (type === 'Page.lifecycleEvent' && event.name === 'load' && event.loaderId === document && held) {
        const events = held;
        held = null;
        setTimeout(() => events.forEach((e) => client.emit('Network.responseReceivedExtraInfo', e)), 100);
      }
      return handled;
    };
    return page;
  };
  try {
    await render({ props: { words: [word('äöü', 0, 0.3)] }, out: join(root, M('media/b/w/p/late.mov')) });
  } finally {
    proto.newPage = newPage;
  }
  assert.ok(late > 0, 'a document\'s response came after its load');
});
