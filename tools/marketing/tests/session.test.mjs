// The session picker in a real browser: a made-up session of three items (an overview, a taste change with two
// reference images and two of ours, a brand line with one of ours), built by taste/build.py with the bundled ffmpeg
// and fonts, then driven at phone width and once at laptop width. Needs the Playwright Chromium
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

const tmp = mkdtempSync(join(tmpdir(), 'mkt-session-'));
const PAGE = 'demo';
const DAY = 'session-2026-01-06';
const REEL = 'DemoCode00M';
const here = join(tmp, 'workspaces/marketing/media/taste', PAGE, DAY);
const url = pathToFileURL(join(here, 'picker.html')).href;
let browser;

const image = (file, colour) => {
  const run = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', `color=c=${colour}:size=1080x1350`, '-frames:v', '1', file]);
  assert.equal(run.status, 0, String(run.stderr));
};

before(() => {
  for (const sub of ['ref', 'ours']) mkdirSync(join(here, sub), { recursive: true });
  mkdirSync(join(tmp, 'tools/marketing'), { recursive: true });
  symlinkSync(fileURLToPath(new URL('../node_modules', import.meta.url)), join(tmp, 'tools/marketing/node_modules'));
  const reel = join(tmp, 'workspaces/marketing/intelligence/reels', REEL);
  mkdirSync(reel, { recursive: true });
  writeFileSync(join(reel, 'style.md'), `style: ${REEL}\nSubtitles: white words\nFlag: none\n`);
  image(join(here, 'ref/t1-1.jpg'), 'navy');
  image(join(here, 'ref/t1-2.jpg'), 'teal');
  image(join(here, 'ours/t1-a.png'), 'maroon');
  image(join(here, 'ours/t1-b.png'), 'olive');
  image(join(here, 'ours/b1-a.png'), 'gray');
  writeFileSync(join(here, 'session.json'), JSON.stringify({
    page: PAGE, title: 'Session 1: demo', intro: 'Three proposals from this week.',
    items: [
      { id: 'o1', part: 'overview', title: 'The week in one line', why: 'Cooking ran x2; talking heads x1.',
        links: [], reference: [], options: [], old: '', new: 'Two cooking reels a week.',
        choices: ['Agree', 'Discuss'], default: 'Agree' },
      { id: 't1', part: 'taste', title: 'Labels on the screen', why: 'Both reels label every part, in large type.',
        links: [`https://www.instagram.com/reel/${REEL}/`],
        reference: [{ src: 'ref/t1-1.jpg', caption: 'cooking, x2', reel: REEL }, { src: 'ref/t1-2.jpg', caption: 'cooking, x3', reel: REEL }],
        options: [{ key: 'A', label: 'Ours: German labels', src: 'ours/t1-a.png' }, { key: 'B', label: 'Ours: English labels', src: 'ours/t1-b.png' }],
        old: 'Labels in French only.', new: 'Labels in French and German.',
        choices: ['Adopt A', 'Adopt B', 'Try', 'Skip'], default: 'Adopt A' },
      { id: 'b1', part: 'brand', title: 'Grey for the code', why: '', links: [], reference: [],
        options: [{ key: 'A', label: 'Ours: grey panels', src: 'ours/b1-a.png' }],
        old: 'Code on black.', new: 'Code on grey.', choices: ['Adopt', 'Skip'], default: 'Adopt' },
    ] }));
  const built = spawnSync('python3', ['-I', '-c',
    'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import build; '
    + 'print(build.build_session(sys.argv[2], sys.argv[3], root=Path(sys.argv[4])))',
    fileURLToPath(new URL('../taste', import.meta.url)), PAGE, join(here, 'session.json'), tmp,
  ], { encoding: 'utf8' });
  assert.equal(built.status, 0, built.stderr);
});

after(async () => {
  await browser?.close();
  rmSync(tmp, { recursive: true, force: true });
});

// A fresh tab with its own storage, the clock under the test's control, and every page error kept.
async function open(width = 390, height = 844) {
  browser ??= await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', (error) => problems.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') problems.push(message.text()); });
  await page.clock.install();
  await page.goto(url);
  return { context, page, problems };
}

const choice = (page, id, text) => page.locator(`[data-id="${id}"] .choice label`, { hasText: new RegExp(`^${text}$`) });
const text = (page) => page.evaluate(() => window.pickerText());
const box = (page, selector) => page.locator(selector).boundingBox();
const noSidewaysScroll = async (page) => {
  const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  assert.ok(scroll <= client, `${scroll} px wide in ${client}`);
};

test('at 390 px: one card an item, no sideways scroll, every image real, ours beside theirs, no errors', async () => {
  const { context, page, problems } = await open();
  assert.equal(await page.locator('.item').count(), 3);
  await noSidewaysScroll(page);
  const images = await page.evaluate(() => [...document.images].filter((i) => i.src).map((i) => i.complete && i.naturalWidth > 0));
  assert.ok(images.length === 5 && images.every(Boolean), String(images));
  assert.ok(await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].some((face) => face.family.includes('Golos') && face.status === 'loaded');
  }));
  const [theirs, ours] = await page.locator('[data-id="t1"] .side').evaluateAll((sides) => sides.map((side) => side.getBoundingClientRect().toJSON()));
  assert.ok(ours.left >= theirs.right && Math.abs(ours.top - theirs.top) < 2, `${JSON.stringify(theirs)} then ${JSON.stringify(ours)}`);
  assert.ok(await page.locator('[data-id="t1"] input[value="Adopt A"]').isChecked());
  assert.ok(await page.locator('[data-id="o1"] input[value="Agree"]').isChecked());
  assert.deepEqual(problems, []);
  await context.close();
});

test('at 1280 px: the images on the left, the answer on the right, no sideways scroll', async () => {
  const { context, page, problems } = await open(1280, 800);
  await noSidewaysScroll(page);
  const compare = await box(page, '[data-id="t1"] .compare');
  const answer = await box(page, '[data-id="t1"] .answer');
  assert.ok(answer.x >= compare.x + compare.width && Math.abs(answer.y - compare.y) < 2, `${JSON.stringify(compare)} then ${JSON.stringify(answer)}`);
  const wide = await box(page, '[data-id="o1"] .answer');
  const head = await box(page, '[data-id="o1"] .head');
  assert.ok(wide.width >= head.width - 1, `${wide.width} px of ${head.width}`);
  assert.deepEqual(problems, []);
  await context.close();
});

test('the change shows what goes and what comes', async () => {
  const { context, page, problems } = await open();
  assert.equal(await page.locator('[data-id="t1"] .change del').textContent(), 'only.');
  assert.equal(await page.locator('[data-id="t1"] .change ins').textContent(), 'and German.');
  assert.ok(await page.locator('[data-id="t1"] .change del').isVisible());
  assert.ok(await page.locator('[data-id="t1"] .change ins').isVisible());
  assert.equal(
    await page.locator('[data-id="t1"] .change del').evaluate((el) => getComputedStyle(el).textDecorationLine), 'line-through');
  assert.match(await page.locator('[data-id="o1"] .change .old').textContent(), /Nothing yet: a new line\./);
  assert.deepEqual(problems, []);
  await context.close();
});

test('a choice and a note survive a reload', async () => {
  const { context, page, problems } = await open();
  await choice(page, 't1', 'Try').click();
  await page.locator('[data-id="b1"] .note').fill('Lighter grey, äöü');
  assert.equal(await page.locator('#changed').textContent(), '1');
  await page.reload();
  assert.ok(await page.locator('[data-id="t1"] input[value="Try"]').isChecked());
  assert.equal(await page.locator('[data-id="b1"] .note').inputValue(), 'Lighter grey, äöü');
  assert.equal(await page.locator('#changed').textContent(), '1');
  assert.match(await page.locator('[data-id="t1"] legend').evaluate((el) => getComputedStyle(el, '::after').content), /changed/);
  const copy = await text(page);
  assert.match(copy, new RegExp(`^Session answers, ${PAGE}, ${DAY}\\. 3 items, 1 changed, 1 notes\\.`));
  assert.match(copy, /\nt1: Try \(changed from Adopt A, touched\)\n/);
  assert.match(copy, /\nb1: Adopt \(the default, touched\)\. Note: Lighter grey, äöü$/);
  assert.deepEqual(problems, []);
  await context.close();
});

test('touched, untouched and minutes survive a reload; the clock stops when idle', async () => {
  const { context, page, problems } = await open();
  await choice(page, 'o1', 'Agree').click(); // already the default: still touched
  const seconds = async () => (await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), `taste-session-${PAGE}-${DAY}`)).seconds;
  await page.clock.runFor(30000);
  const active = await seconds();
  assert.ok(active >= 20 && active <= 30, `${active} s after 30 s of use`);
  await page.clock.runFor(600000);
  const idle = await seconds();
  assert.ok(idle >= active && idle <= 65, `${idle} s after ten idle minutes`);
  await page.reload();
  const copy = await text(page);
  assert.match(copy, new RegExp(`Minutes on this page: ${Math.ceil(idle / 60)}\\.`));
  assert.match(copy, /\no1: Agree \(the default, touched\)\n/);
  assert.match(copy, /\nt1: Adopt A \(the default, untouched\)\n/);
  assert.match(copy, /\nb1: Adopt \(the default, untouched\)$/);
  assert.deepEqual(problems, []);
  await context.close();
});

test('Copy puts exactly the page\'s text on the clipboard', async () => {
  const { context, page, problems } = await open();
  await choice(page, 'b1', 'Skip').click();
  await page.locator('#copy').click();
  await page.waitForTimeout(200);
  assert.equal(await page.locator('#copy').textContent(), 'Copied');
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  assert.equal(copied, await text(page));
  assert.match(copied, /\nb1: Skip \(changed from Adopt, touched\)$/);
  assert.deepEqual(problems, []);
  await context.close();
});

test('a reference image and one of ours open large, and a tap closes them', async () => {
  const { context, page, problems } = await open();
  const zoomed = () => page.locator('#zoom').evaluate((dialog) => dialog.open);
  for (const side of [1, 2]) {
    const figure = page.locator(`[data-id="t1"] .side:nth-child(${side}) .figs img`).first();
    await figure.click();
    assert.ok(await zoomed(), `side ${side}`);
    assert.equal(await page.locator('#zoom img').getAttribute('src'), await figure.getAttribute('src'));
    await page.locator('#zoom').click();
    assert.ok(!(await zoomed()), `side ${side}`);
  }
  assert.deepEqual(problems, []);
  await context.close();
});

// The welcome doesn't send him to the computer, as the trial's doesn't.
test('the welcome works for a phone', async () => {
  const { context, page, problems } = await open();
  const welcome = await page.locator('.intro').textContent();
  assert.match(welcome, /It works in Chrome on your computer or in your phone's browser\. Your answers stay on the device where you started/);
  assert.doesNotMatch(welcome, /Use your computer/);
  const noscript = readFileSync(join(here, 'picker.html'), 'utf8').match(/<noscript>(.*?)<\/noscript>/s)[1];
  assert.match(noscript, /in Chrome on your computer or in your phone's browser; your answers stay on the device where you start/);
  assert.doesNotMatch(noscript, /Open the file on your computer\./);
  assert.deepEqual(problems, []);
  await context.close();
});
