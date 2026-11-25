// The taste picker in a real browser: a made-up page of four items (reel, carousel, post, story), built by
// taste/build.py with the bundled ffmpeg and fonts, then driven at phone width. Needs the Playwright Chromium
// (npx playwright install chromium); not run in CI.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after, before } from 'node:test';
import ffmpeg from 'ffmpeg-static';
import { chromium } from 'playwright';

const tmp = mkdtempSync(join(tmpdir(), 'mkt-taste-'));
const PAGE = 'demo';
const REEL = 'DemoCode00M';
const CAROUSEL = 'CzAbCdEfGhI';
const POST = 'CzPlainPost';
const STORY = 'StOrYcOdE12';
const folder = join(tmp, 'workspaces/marketing/media/taste', PAGE);
const url = pathToFileURL(join(folder, 'picker.html')).href;
let browser;

const make = (args) => {
  const run = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', ...args]);
  assert.equal(run.status, 0, String(run.stderr));
};
const video = (file, seconds) => make(['-i', `testsrc2=size=720x1280:rate=10:duration=${seconds}`, '-pix_fmt', 'yuv420p', file]);
const image = (file, colour) => make(['-i', `color=c=${colour}:size=1080x1350`, '-frames:v', '1', file]);
const style = (code) => `style: ${code}\nFrames: 1, 5, 8, 15, 19, 23\nSubtitles: Weiße Schrift, äöü, the active word in yellow\nFlag: none\n`;

function reel(code) {
  const dir = join(tmp, 'workspaces/marketing/intelligence/reels', code);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'style.md'), style(code));
  writeFileSync(join(dir, 'metrics.json'), JSON.stringify({
    account: 'someone.real', multiple: 12.5, length_seconds: 30, sheet_whole: { columns: 6, rows: 4, seconds_per_tile: 1.2 } }));
  writeFileSync(join(dir, 'breakdown.md'), 'format: talking head\n');
  writeFileSync(join(dir, 'caption.txt'), 'Neues Wort, ein oder zwei Ideen.');
  video(join(dir, 'video.mp4'), 30);
}

function post(code, kind, slides, cover) {
  const dir = join(tmp, 'workspaces/marketing/intelligence/posts', code);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'style.md'), style(code));
  const entries = slides.map((colour, i) => {
    if (colour) {
      image(join(dir, `${i + 1}.jpg`), colour);
      return { file: `${i + 1}.jpg`, type: 'image' };
    }
    video(join(dir, `${i + 1}.mp4`), 8);
    return { file: `${i + 1}.mp4`, type: 'video', seconds: 8 };
  });
  if (cover) image(join(dir, 'cover.jpg'), 'orange');
  writeFileSync(join(dir, 'MANIFEST.json'), JSON.stringify({
    kind, code, account: 'someone.real', date: '2026-01-05', description: 'Karussell: fünf Ideen, drei Bilder.',
    cover: cover ? 'cover.jpg' : null, slides: entries }));
}

before(() => {
  mkdirSync(folder, { recursive: true });
  mkdirSync(join(tmp, 'tools/marketing'), { recursive: true });
  symlinkSync(fileURLToPath(new URL('../node_modules', import.meta.url)), join(tmp, 'tools/marketing/node_modules'));
  reel(REEL);
  post(CAROUSEL, 'carousel', ['navy', 'teal', null, 'maroon'], true);
  post(POST, 'post', ['gray'], false);
  post(STORY, 'story', [null], false);
  writeFileSync(join(folder, 'rubric.json'), JSON.stringify({
    title: 'Your taste: demo', intro: 'I chose for you.', assumed: ['You like short cards.'],
    page_questions: [
      { key: 'length', question: 'How long should reels run?', options: ['Under 30 s', '30-60 s'], default: '30-60 s' },
      { key: 'slides', question: 'How many slides in a carousel?', options: ['5', '7', '10'], default: '7' },
    ],
    aspects: [
      { key: 'subs', label: 'Subtitles', kinds: ['reel', 'story'], from: 'style:Subtitles' },
      { key: 'desc', label: 'Description', kinds: ['reel', 'carousel', 'post', 'story'], from: 'description' },
      { key: 'long', label: 'Length', kinds: ['reel', 'story', 'carousel'], from: 'seconds' },
      { key: 'cover', label: 'Cover', kinds: ['carousel', 'post'], from: 'cover' },
    ] }));
  writeFileSync(join(folder, 'picks.json'), JSON.stringify({ round: 1, items: [
    { code: REEL, kind: 'reel', picks: { subs: 'L', desc: 'D', long: 'L' } },
    { code: CAROUSEL, kind: 'carousel', picks: { desc: 'L', long: 'L', cover: 'L' } },
    { code: POST, kind: 'post', picks: { desc: 'L' } },
    { code: STORY, kind: 'story', picks: { subs: 'D', long: 'L' } },
  ] }));
  const built = spawnSync('python3', ['-I', '-c',
    'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import build; '
    + 'print(build.build(sys.argv[2], sys.argv[3], sys.argv[4], root=Path(sys.argv[5])))',
    fileURLToPath(new URL('../taste', import.meta.url)), PAGE, join(folder, 'rubric.json'), join(folder, 'picks.json'), tmp,
  ], { encoding: 'utf8' });
  assert.equal(built.status, 0, built.stderr);
});

after(async () => {
  await browser?.close();
  rmSync(tmp, { recursive: true, force: true });
});

// A fresh phone-sized tab with its own storage, the clock under the test's control, and every page error kept.
async function open() {
  browser ??= await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', (error) => problems.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') problems.push(message.text()); });
  await page.clock.install();
  await page.goto(url);
  return { context, page, problems };
}

const option = (page, code, aspect, word) =>
  page.locator(`[data-code="${code}"] [data-aspect="${aspect}"] label`, { hasText: new RegExp(`^${word}$`) });
const answer = (page, key, text) => page.locator(`.question[data-key="${key}"] label`, { hasText: new RegExp(`^${text}$`) });
const text = (page) => page.evaluate(() => window.pickerText());

test('at 390 px: no sideways scroll, every image real, the font loaded, no errors', async () => {
  const { context, page, problems } = await open();
  assert.equal(await page.locator('.item').count(), 4);
  assert.equal(await page.locator('.question').count(), 2);
  const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  assert.ok(scroll <= client, `${scroll} px wide in ${client}`);
  const images = await page.evaluate(() => [...document.images].filter((i) => i.src).map((i) => i.complete && i.naturalWidth > 0));
  assert.ok(images.length >= 12 && images.every(Boolean), String(images)); // six frames, four slides, a post, a story, a cover
  assert.ok(await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].some((face) => face.family.includes('Golos') && face.status === 'loaded');
  }));
  assert.deepEqual(problems, []);
  await context.close();
});

test('choices, a note and a page answer survive a reload', async () => {
  const { context, page, problems } = await open();
  await option(page, REEL, 'subs', 'Disliked').click();
  await page.locator(`[data-code="${POST}"] .note`).fill('Too plain, äöü');
  await answer(page, 'slides', '10').click();
  assert.equal(await page.locator('#changed').textContent(), '1');
  await page.reload();
  assert.ok(await page.locator(`[data-code="${REEL}"] [data-aspect="subs"] input[value="D"]`).isChecked());
  assert.equal(await page.locator(`[data-code="${POST}"] .note`).inputValue(), 'Too plain, äöü');
  assert.ok(await page.locator('.question[data-key="slides"] input[value="10"]').isChecked());
  assert.equal(await page.locator('#changed').textContent(), '1');
  const copy = await text(page);
  assert.match(copy, /1 choices changed, 1 notes/);
  assert.match(copy, /How many slides in a carousel\?: 10 \(chosen\)/);
  assert.match(copy, /Note: Too plain, äöü/);
  assert.deepEqual(problems, []);
  await context.close();
});

test('touched, left and minutes survive a reload; the clock stops when idle', async () => {
  const { context, page, problems } = await open();
  await option(page, REEL, 'subs', 'Disliked').click();
  await option(page, CAROUSEL, 'desc', 'Liked').click(); // already Liked: still touched
  const seconds = async () => (await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), `taste-picker-${PAGE}-round-1`)).seconds;
  await page.clock.runFor(30000);
  const active = await seconds();
  assert.ok(active >= 20 && active <= 30, `${active} s after 30 s of use`);
  await page.clock.runFor(600000);
  const idle = await seconds();
  assert.ok(idle >= active && idle <= 65, `${idle} s after ten idle minutes`);
  await page.reload();
  const copy = await text(page);
  assert.match(copy, new RegExp(`Minutes on this page: ${Math.ceil(idle / 60)}\\.`));
  assert.match(copy, new RegExp(`Touched: ${REEL}, ${CAROUSEL}\n`));
  assert.match(copy, new RegExp(`Left as pre-selected: ${POST}, ${STORY}\n`));
  assert.deepEqual(problems, []);
  await context.close();
});

test('a page answer tapped on its default copies as chosen, after a reload too', async () => {
  const { context, page, problems } = await open();
  await answer(page, 'length', '30-60 s').click();
  for (const pass of ['before', 'after']) {
    const copy = await text(page);
    assert.match(copy, /How long should reels run\?: 30-60 s \(chosen\)/, `${pass} the reload`);
    assert.match(copy, /How many slides in a carousel\?: 7 \(pre-selected\)/, `${pass} the reload`);
    if (pass === 'before') await page.reload();
  }
  assert.deepEqual(problems, []);
  await context.close();
});

test('Copy puts exactly the page\'s text on the clipboard', async () => {
  const { context, page, problems } = await open();
  await option(page, STORY, 'subs', 'Liked').click();
  await page.locator('#copy').click();
  await page.waitForTimeout(200);
  assert.equal(await page.locator('#copy').textContent(), 'Copied');
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await text(page));
  assert.deepEqual(problems, []);
  await context.close();
});

test('a frame and a cover open large, and a tap closes them', async () => {
  const { context, page, problems } = await open();
  const zoomed = () => page.locator('#zoom').evaluate((dialog) => dialog.open);
  await page.locator(`[data-code="${REEL}"] .frames img`).first().click();
  assert.ok(await zoomed());
  assert.equal(await page.locator('#zoom img').getAttribute('src'),
    await page.locator(`[data-code="${REEL}"] .frames img`).first().getAttribute('src'));
  await page.locator('#zoom').click();
  assert.ok(!(await zoomed()));
  await page.locator(`[data-code="${CAROUSEL}"] [data-aspect="cover"] .seen img`).click();
  assert.ok(await zoomed());
  await page.locator('#zoom').click();
  assert.ok(!(await zoomed()));
  assert.deepEqual(problems, []);
  await context.close();
});

// The welcome doesn't send him to the computer, as the trial's doesn't.
test('the welcome works for a phone', async () => {
  const { context, page, problems } = await open();
  const welcome = await page.locator('.intro').textContent();
  assert.match(welcome, /It works in Chrome on your computer or in your phone's browser\. Your choices stay on the device where you started/);
  assert.doesNotMatch(welcome, /Use your computer/);
  const noscript = readFileSync(join(folder, 'picker.html'), 'utf8').match(/<noscript>(.*?)<\/noscript>/s)[1];
  assert.match(noscript, /in Chrome on your computer or in your phone's browser; your choices stay on the device where you start/);
  assert.doesNotMatch(noscript, /Open the file on your computer\./);
  assert.deepEqual(problems, []);
  await context.close();
});
