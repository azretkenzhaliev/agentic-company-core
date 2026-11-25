// The trial page in a real browser: the committed example session (taste/example-trial.json), built by
// taste/build.py with a made-up image or VP9 video at every file it names, then judged end to end at laptop width:
// every trial type, a break, a reload in the middle, the Parts menu, and the downloaded answers. Needs the Playwright
// Chromium (npx playwright install chromium); not run in CI. Playwright's Chromium has no H.264, so the videos are VP9
// in .mp4 files; Chrome plays both.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after, before } from 'node:test';
import ffmpeg from 'ffmpeg-static';
import { chromium } from 'playwright';

const tmp = mkdtempSync(join(tmpdir(), 'mkt-trial-'));
const PAGE = 'demo';
const DAY = 'session-2026-01-07';
const here = join(tmp, 'workspaces/marketing/media/taste', PAGE, DAY);
const url = pathToFileURL(join(here, 'picker.html')).href;
const example = JSON.parse(readFileSync(new URL('../taste/example-trial.json', import.meta.url), 'utf8'));
let browser;
let design;

const run = (args) => spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', ...args], { encoding: 'utf8' });
const python = (designOnly) => spawnSync('python3', ['-I', '-c',
  'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import build; '
  + 'print(build.build_session(sys.argv[2], sys.argv[3], root=Path(sys.argv[4]), design_only=sys.argv[5] == "1"))',
  fileURLToPath(new URL('../taste', import.meta.url)), PAGE, join(here, 'session.json'), tmp, designOnly ? '1' : '0',
], { encoding: 'utf8' });

function codes(value, found = new Set()) {
  if (Array.isArray(value)) value.forEach((inner) => codes(inner, found));
  else if (value && typeof value === 'object') {
    for (const kind of ['reel', 'post']) if (typeof value[kind] === 'string') found.add(kind + 's/' + value[kind]);
    Object.values(value).forEach((inner) => codes(inner, found));
  }
  return found;
}

before(() => {
  mkdirSync(here, { recursive: true });
  mkdirSync(join(tmp, 'tools/marketing'), { recursive: true });
  symlinkSync(fileURLToPath(new URL('../node_modules', import.meta.url)), join(tmp, 'tools/marketing/node_modules'));
  for (const code of codes(example)) {
    const folder = join(tmp, 'workspaces/marketing/intelligence', code);
    mkdirSync(folder, { recursive: true });
    writeFileSync(join(folder, 'style.md'), `style: ${code}\nFlag: none\n`);
  }
  writeFileSync(join(here, 'session.json'), JSON.stringify(example));
  const planned = python(true);
  assert.equal(planned.status, 0, planned.stderr);
  const { files, missing } = JSON.parse(planned.stdout);
  assert.deepEqual(missing, files);
  // A few made-up images and videos, copied to every file the session names. The single posts are 9:16 stills, as
  // a story is.
  const samples = { jpg: [], mp4: [], tall: [] };
  ['navy', 'teal', 'maroon', 'olive'].forEach((colour, k) => {
    const still = join(tmp, `sample-${k}.jpg`);
    let made = run(['-i', `color=c=${colour}:size=540x675`, '-frames:v', '1', still]);
    assert.equal(made.status, 0, made.stderr);
    samples.jpg.push(still);
    const tall = join(tmp, `sample-${k}-tall.jpg`);
    made = run(['-i', `color=c=${colour}:size=360x640`, '-frames:v', '1', tall]);
    assert.equal(made.status, 0, made.stderr);
    samples.tall.push(tall);
    const moving = join(tmp, `sample-${k}.mp4`);
    made = run(['-i', `testsrc2=size=360x640:rate=24,hue=h=${k * 90}`, '-t', '2', '-c:v', 'libvpx-vp9', '-deadline', 'realtime',
      '-cpu-used', '8', '-b:v', '300k', '-pix_fmt', 'yuv420p', '-an', moving]);
    assert.equal(made.status, 0, made.stderr);
    samples.mp4.push(moving);
  });
  files.forEach((file, k) => {
    mkdirSync(dirname(join(here, file)), { recursive: true });
    const kind = file.endsWith('.mp4') ? 'mp4' : file.startsWith('ours/post-') ? 'tall' : 'jpg';
    copyFileSync(samples[kind][k % 4], join(here, file));
  });
  const built = python(false);
  assert.equal(built.status, 0, built.stderr);
  assert.match(built.stdout, /^wrote .*picker\.html: 14 parts, \d+ trials, \d+ media files, seed 12345/);
});

after(async () => {
  await browser?.close();
  rmSync(tmp, { recursive: true, force: true });
});

async function open(viewport = { width: 1280, height: 800 }, init = null) {
  browser ??= await chromium.launch();
  const context = await browser.newContext({ viewport, acceptDownloads: true });
  if (init) await context.addInitScript(init);
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', (error) => problems.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') problems.push(message.text()); });
  page.on('requestfailed', (request) => problems.push('failed: ' + request.url()));
  await page.clock.install();
  await page.goto(url);
  design ??= await page.evaluate(() => JSON.parse(document.getElementById('design').textContent));
  return { context, page, problems };
}

const KEY = () => `taste-trial-${PAGE}-${DAY}-${design.design_id}`;
const saved = (page) => page.evaluate((key) => JSON.parse(localStorage.getItem(key)), KEY());
const partOf = (id) => design.parts.find((part) => part.trials.some((trial) => trial.id === id));
const trialOf = (id) => partOf(id).trials.find((trial) => trial.id === id);
const flip = (page, scope, text) => page.locator(scope).getByRole('button', { name: text, exact: true });

// Each trial type answered by one fixed rule, so the downloaded answers can be checked against it.
async function judge(page, id, checks) {
  const part = partOf(id);
  const trial = trialOf(id);
  assert.equal(await page.locator('.mine, .flip.on').count(), 0, `${id} starts with something chosen`);
  if (part.type === 'pairwise') await page.keyboard.press('1');
  else if (part.type === 'cbc') {
    if (checks.video && part.trials[0].id === id && trial.options[0].media === 'video') {
      const widths = await page.locator('video').evaluateAll((videos) => Promise.all(videos.map((video) => new Promise((done) => {
        if (video.readyState >= 2) done([video.videoWidth, video.muted]);
        else video.addEventListener('loadeddata', () => done([video.videoWidth, video.muted]));
      }))));
      assert.deepEqual(widths, [[360, true], [360, true], [360, true]]);
      checks.video = false;
    }
    await page.keyboard.press('2');
  } else if (part.type === 'maxdiff') {
    const next = page.locator('button.next');
    assert.ok(await next.isDisabled());
    await flip(page, `.option[data-id="${trial.items[0]}"]`, 'Best').click();
    assert.ok(await next.isDisabled(), 'Next before a worst');
    await flip(page, `.option[data-id="${trial.items[3]}"]`, 'Worst').click();
    await next.click();
  } else if (part.type === 'sequence') {
    if (checks.images) {
      // Waits for every image to finish, loaded or not: read at once, a slow one sometimes failed.
      await page.waitForFunction(() => [...document.images].filter((i) => i.closest('.option')).every((i) => i.complete));
      const loaded = await page.evaluate(() => [...document.images].filter((i) => i.closest('.option')).map((i) => i.complete && i.naturalWidth > 0));
      assert.ok(loaded.length === 7 && loaded.every(Boolean), String(loaded));
      checks.images = false;
    }
    for (const step of [2, 4, 3]) await flip(page, `.option[data-step="${step}"]`, 'Fine').click();
    assert.ok(await page.locator('button.next').isDisabled(), 'Next before a best');
    await flip(page, '.option[data-step="3"]', 'Best').click();
    await page.locator('button.next').click();
  } else if (part.type === 'range') {
    const dimension = part.dimensions.find((entry) => entry.id === trial.dimension);
    if (dimension.ordered) {
      await flip(page, '.value[data-value="1"]', 'Fine').click();
      await flip(page, '.value[data-value="2"]', 'Best').click();
    } else {
      await flip(page, '.value[data-value="0"]', 'Fine').click();
      await flip(page, '.value[data-value="2"]', 'Fine').click();
    }
    await page.locator('button.next').click();
  } else if (part.type === 'notes') {
    await page.locator('textarea.note').fill(`A note on ${trial.item}, äöü`);
    await page.locator('button.next').click();
  } else if (part.type === 'redlines') {
    await flip(page, '.value:first-child', 'Hard no').click();
    await page.locator('textarea.note').fill('No fake urgency\n\nNo stock photos ');
    await page.locator('button.next').click();
  } else {
    await flip(page, '.value:last-child', part.mark).click();
    await page.locator('button.next').click();
  }
}

// Through the whole sitting from where the page opens: reads where it is from its own saved state, never from the
// screen's text.
async function sitting(page, { stopAfter = Infinity, checks = { video: true, images: true } } = {}) {
  let judged = 0;
  let intros = 0;
  for (;;) {
    const state = await saved(page);
    if (state.on_break) {
      assert.match(await page.locator('#screen h1').textContent(), /^A break$/);
      await page.getByRole('button', { name: 'Go on' }).click();
    } else if (state.where === 'welcome') await page.getByRole('button', { name: /^(Start|Go on)$/ }).click();
    else if (state.where.startsWith('intro:')) {
      intros += 1;
      await page.getByRole('button', { name: intros === 1 ? 'Start' : 'Skip intros from now on' }).click();
    } else if (state.where === 'end') return judged;
    else {
      await judge(page, state.where, checks);
      judged += 1;
      if (judged === stopAfter) return judged;
    }
  }
}

test('the example, end to end: every type, a break, a reload, and every answer in the download', async () => {
  const { context, page, problems } = await open();
  const total = design.parts.reduce((sum, part) => sum + part.trials.length, 0);
  assert.equal(await page.locator('#total').textContent(), String(total));
  assert.equal(await page.locator('input:checked, [aria-pressed="true"]').count(), 0);

  // Twelve trials in, twenty-three minutes of steady judging: the next trial is a break.
  let judged = await sitting(page, { stopAfter: 12 });
  for (let k = 0; k < 14; k += 1) {
    await page.keyboard.press('Shift');
    await page.clock.runFor(100000);
  }
  const before = await saved(page);
  assert.ok(before.since_break >= 22 * 60, `${before.since_break} s judged`);
  assert.ok(await page.locator('#clock').evaluate((clock) => clock.classList.contains('over')));

  // A reload opens the same screen with every answer kept.
  await page.reload();
  const after = await saved(page);
  assert.equal(after.where, before.where);
  assert.equal(Object.keys(after.answers).length, 12);
  assert.equal(await page.locator('#done').textContent(), '12');
  judged += await sitting(page);
  assert.equal(judged, total);
  const state = await saved(page);
  assert.equal(state.breaks.length, 1);
  assert.equal(state.intros.p0.skipped, false);
  assert.equal(state.intros.p1.skipped, true);
  assert.ok(design.parts.every((part) => !part.intro.length || part.id in state.intros));

  const download = page.waitForEvent('download');
  await page.locator('#save').click();
  const file = await download;
  assert.equal(file.suggestedFilename(), `answers-${PAGE}-${DAY}.json`);
  const answers = JSON.parse(readFileSync(await file.path(), 'utf8'));
  assert.equal(answers.format, 'taste-trial-answers-1');
  assert.equal(answers.design_id, design.design_id);
  assert.equal(answers.seed, 12345);
  assert.deepEqual(answers.design, design);
  assert.equal(Object.keys(answers.answers).length, total);
  for (const part of design.parts) {
    for (const trial of part.trials) {
      const given = answers.answers[trial.id];
      assert.ok(given.ms >= 0 && given.at, trial.id);
      if (part.type === 'pairwise') assert.equal(given.pick, trial.items[0], trial.id);
      if (part.type === 'cbc') assert.equal(given.pick, 2, trial.id);
      if (part.type === 'maxdiff') assert.deepEqual([given.best, given.worst], [trial.items[0], trial.items[3]], trial.id);
      if (part.type === 'sequence') assert.deepEqual([given.best, given.from, given.to], [4, 3, 5], trial.id);
      if (part.type === 'range') {
        const { values, ordered } = part.dimensions.find((entry) => entry.id === trial.dimension);
        assert.deepEqual(given, { ...(ordered ? { from: values[1], to: values[2], best: values[2] } : { fine: [values[0], values[2]], best: null }),
          ms: given.ms, at: given.at }, trial.id);
      }
      if (part.type === 'notes') assert.equal(given.note, `A note on ${trial.item}, äöü`);
      if (part.type === 'redlines') assert.deepEqual([given.checked, given.own], [[trial.candidates[0]], ['No fake urgency', 'No stock photos']]);
      if (part.type === 'checklist') assert.deepEqual([given.checked, given.own, trial.candidates], [[part.candidates.at(-1)], [], part.candidates]);
    }
  }
  assert.ok(answers.judging_seconds >= 22 * 60 && answers.part_seconds[partOf(before.where).id] >= 22 * 60);
  writeFileSync(join(here, 'answers.json'), JSON.stringify(answers));
  assert.deepEqual(problems, []);
  await context.close();
});

test('Parts goes anywhere; Back shows the answer given, which stands unless changed', async () => {
  const { context, page, problems } = await open();
  await sitting(page, { stopAfter: 3 });
  await page.locator('#menu').click();
  const rows = page.locator('#parts .value');
  assert.equal(await rows.count(), design.parts.length);
  assert.match(await rows.first().textContent(), /: 3 of 6/);
  await rows.last().getByRole('button', { name: 'Start' }).click();
  const last = design.parts.at(-1);
  assert.match((await saved(page)).where, new RegExp(`^(intro:${last.id}|${last.trials[0].id})$`));
  await page.locator('#menu').click();
  await rows.first().getByRole('button', { name: 'Go on' }).click();
  assert.equal((await saved(page)).where, design.parts[0].trials[3].id);
  await page.locator('#back').click();
  const id = design.parts[0].trials[2].id;
  assert.equal((await saved(page)).where, id);
  const first = await saved(page);
  assert.equal(await page.locator('.option.mine').count(), 1);
  await page.getByRole('button', { name: 'Keep my answer' }).click();
  assert.deepEqual((await saved(page)).answers[id], first.answers[id]);
  await page.locator('#back').click();
  await page.keyboard.press('2');
  const changed = (await saved(page)).answers[id];
  assert.equal(changed.pick, trialOf(id).items[1]);
  assert.equal(changed.revised, true);
  assert.deepEqual(problems, []);
  await context.close();
});

test('a break comes going forward, never on Back', async () => {
  const { context, page, problems } = await open();
  await sitting(page, { stopAfter: 3 });
  for (let k = 0; k < 14; k += 1) {
    await page.keyboard.press('Shift');
    await page.clock.runFor(100000);
  }
  assert.ok((await saved(page)).since_break >= 22 * 60);
  await page.locator('#back').click();
  const back = await saved(page);
  assert.deepEqual([back.on_break, back.where], [false, design.parts[0].trials[2].id]);
  await page.getByRole('button', { name: 'Keep my answer' }).click();
  const on = await saved(page);
  assert.deepEqual([on.on_break, on.where], [true, design.parts[0].trials[3].id]);
  assert.match(await page.locator('#screen h1').textContent(), /^A break$/);
  // Back on the break screen goes back; the break is recorded only on Go on.
  await page.locator('#back').click();
  const left = await saved(page);
  assert.deepEqual([left.on_break, left.where, left.breaks.length], [false, design.parts[0].trials[2].id, 0]);
  assert.ok(left.since_break >= 22 * 60, `${left.since_break} s: Back doesn't reset the clock`);
  assert.doesNotMatch(await page.locator('#screen h1').textContent(), /^A break$/);
  await page.getByRole('button', { name: 'Keep my answer' }).click();
  const again = await saved(page);
  assert.deepEqual([again.on_break, again.where], [true, design.parts[0].trials[3].id]);
  await page.getByRole('button', { name: 'Go on' }).click();
  const went = await saved(page);
  assert.deepEqual([went.on_break, went.where, went.breaks.length], [false, design.parts[0].trials[3].id, 1]);
  assert.ok(went.since_break < 60, `${went.since_break} s after Go on`);
  assert.deepEqual(problems, []);
  await context.close();
});

test('the clock counts only while someone is judging', async () => {
  const { context, page, problems } = await open();
  await sitting(page, { stopAfter: 1 });
  await page.keyboard.press('Shift');
  await page.clock.runFor(60000);
  const active = (await saved(page)).judging_seconds;
  assert.ok(active >= 50 && active <= 60, `${active} s after a minute of use`);
  await page.clock.runFor(600000);
  const idle = (await saved(page)).judging_seconds;
  assert.ok(idle <= active + 65, `${idle} s after ten idle minutes`);
  assert.deepEqual(problems, []);
  await context.close();
});

// From a ux check:
// on a phone and a tablet, every Best and Fine of a sequence trial is the button a tap at its centre lands on, stays
// inside its step's box, and the page doesn't scroll sideways; the trial's question is the screen's h1.
test('a sequence trial at 390 and 768 px: every Best and Fine tappable, nothing sideways, the question as the h1', async () => {
  for (const width of [390, 768]) {
    const { context, page, problems } = await open({ width, height: 844 });
    const k = design.parts.findIndex((part) => part.type === 'sequence');
    await page.locator('#menu').click();
    await page.locator('#parts .value').nth(k).getByRole('button', { name: 'Start' }).click();
    if ((await saved(page)).where.startsWith('intro:')) await page.locator('#screen').getByRole('button', { name: 'Start' }).click();
    assert.equal(partOf((await saved(page)).where).type, 'sequence');
    const misses = await page.evaluate(() => [...document.querySelectorAll('.choices.steps .flip')].flatMap((flip) => {
      flip.scrollIntoView({ block: 'center', inline: 'center' });
      const box = flip.getBoundingClientRect();
      const step = flip.closest('.option').getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      const name = `${flip.textContent} of step ${flip.closest('.option').dataset.step}`;
      return [...(hit === flip ? [] : [`${name}: a tap lands on ${hit?.textContent}`]),
        ...(box.left >= step.left - 0.5 && box.right <= step.right + 0.5 ? [] : [`${name}: outside its step`])];
    }));
    assert.equal(await page.locator('.choices.steps .flip').count(), 14);
    assert.deepEqual(misses, [], `${width} px`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, `${width} px`);
    assert.deepEqual(await page.locator('#screen h1').allTextContents(), [design.parts[k].question], `${width} px`);
    assert.equal(await page.locator('#screen h1').evaluate((h1) => getComputedStyle(h1).fontSize), '21px');
    // The detail's name is an h2 under the h1, never a skipped level.
    assert.equal(await page.locator('#screen h3').count(), 0);
    assert.equal(await page.locator('#screen h2.dimension').count(), 1);
    assert.deepEqual(problems, []);
    await context.close();
  }
});

// At a phone's width the screen isn't scrolled, the footer stays 80 px or less, and three options with their buttons
// sit in one row above it.
async function assertOneRowAboveFooter(page, what) {
  const layout = await page.evaluate(() => {
    const bar = document.querySelector('.bar').getBoundingClientRect();
    const boxes = (selector) => [...document.querySelectorAll(selector)].map((node) => {
      const { top, bottom, left, right } = node.getBoundingClientRect();
      return { top, bottom, left, right };
    });
    return { scrollY: window.scrollY, bar: { top: bar.top, height: bar.height }, picks: boxes('#screen .pick'),
      media: boxes('#screen .option video, #screen .option img') };
  });
  assert.equal(layout.scrollY, 0, what);
  assert.ok(layout.bar.height <= 80, `${what}: the footer is ${layout.bar.height} px`);
  assert.equal(layout.picks.length, 3, what);
  assert.equal(layout.media.length, 3, what);
  assert.equal(new Set(layout.picks.map((box) => Math.round(box.top))).size, 1, `${what}: the three buttons in one row`);
  for (const box of [...layout.picks, ...layout.media]) {
    assert.ok(box.top >= 0 && box.bottom <= layout.bar.top, `${what}: ${JSON.stringify(box)} under the footer at ${layout.bar.top}`);
  }
}

// From a ux check:
// the welcome doesn't send him to the computer, the footer stays short with its count on one line, and three reels with
// their buttons sit above it.
test('at 390 px: the welcome works for a phone, the footer stays short, three reels in one row above it', async () => {
  const { context, page, problems } = await open({ width: 390, height: 844 });
  const welcome = await page.locator('#screen').textContent();
  assert.match(welcome, /in your phone's browser/);
  assert.match(welcome, /stay on the device where you started/);
  assert.doesNotMatch(welcome, /Use your computer/);
  const noscript = readFileSync(join(here, 'picker.html'), 'utf8').match(/<noscript>(.*?)<\/noscript>/s)[1];
  assert.match(noscript, /in Chrome on your computer or in your phone's browser; your answers stay on the device where you start/);
  assert.doesNotMatch(noscript, /on your computer, in Chrome/);
  const k = design.parts.findIndex((part) => part.type === 'cbc' && part.trials[0].options[0].media === 'video'
    && part.trials[0].options.length === 3);
  assert.ok(k >= 0, 'the example has a three-reel part');
  await page.locator('#menu').click();
  await page.locator('#parts .value').nth(k).getByRole('button', { name: 'Start' }).click();
  if ((await saved(page)).where.startsWith('intro:')) await page.locator('#screen').getByRole('button', { name: 'Start' }).click();
  assert.equal(partOf((await saved(page)).where).id, design.parts[k].id);
  await page.waitForFunction(() => [...document.querySelectorAll('#screen video')].every((video) => video.readyState >= 1));
  await assertOneRowAboveFooter(page, 'reels');
  assert.equal(await page.locator('#screen .option video').count(), 3);
  // Out of sight, the save status still reaches a screen reader.
  assert.match(await page.locator('.bar .state').ariaSnapshot(), /Saved on this device after every trial\./);
  // The count stays on one line, none of it cut off, even with every trial answered, and with
  // three digits on both sides.
  const total = String(design.parts.reduce((sum, part) => sum + part.trials.length, 0));
  for (const [done, of] of [['0', total], [total, total], ['888', '888']]) {
    await page.locator('#done').evaluate((node, value) => { node.textContent = value; }, done);
    await page.locator('#total').evaluate((node, value) => { node.textContent = value; }, of);
    const count = await page.locator('.bar .state').evaluate((state) => ({
      lines: Math.round(state.getBoundingClientRect().height / parseFloat(getComputedStyle(state).lineHeight)),
      cut: state.scrollWidth > state.clientWidth,
    }));
    assert.deepEqual(count, { lines: 1, cut: false }, await page.locator('.bar .state').textContent());
  }
  assert.ok((await page.locator('.bar').boundingBox()).height <= 80);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0);
  assert.deepEqual(problems, []);
  await context.close();
});

// Three 9:16 stills (the example's single posts) sit in one row at 390 px too, on every trial
// of their part.
test('at 390 px: three tall stills in one row above the footer, on every trial', async () => {
  const { context, page, problems } = await open({ width: 390, height: 844 });
  const k = design.parts.findIndex((part) => part.id === 'p3c');
  const part = design.parts[k];
  assert.ok(part.trials.every((trial) => trial.options.length === 3 && trial.options.every((option) => option.media === 'image')));
  await page.locator('#menu').click();
  await page.locator('#parts .value').nth(k).getByRole('button', { name: 'Start' }).click();
  if ((await saved(page)).where.startsWith('intro:')) await page.locator('#screen').getByRole('button', { name: 'Start' }).click();
  for (const trial of part.trials) {
    assert.equal((await saved(page)).where, trial.id);
    await page.waitForFunction(() => [...document.querySelectorAll('#screen .option img')].every((img) => img.complete && img.naturalWidth > 0));
    // The row takes its shape once trial.js has read the stills'.
    await page.locator('#screen .choices.tall').waitFor({ timeout: 5000 });
    await assertOneRowAboveFooter(page, trial.id);
    await page.keyboard.press('2');
  }
  assert.equal(Object.keys((await saved(page)).answers).length, part.trials.length);
  assert.deepEqual(problems, []);
  await context.close();
});

// Marks each image once its load event has run, so "not marked tall" can't mean "not looked at yet".
const markLoaded = () => document.addEventListener('load', (event) => {
  if (event.target instanceof HTMLImageElement) event.target.dataset.loaded = '1';
}, true);

// A row of 4:5 stills isn't marked tall. A rule that always added the class fails
// here; code with no such class passes.
test('at 390 px: a row of three 4:5 stills is not marked tall', async () => {
  const { context, page, problems } = await open({ width: 390, height: 844 }, markLoaded);
  const k = design.parts.findIndex((part) => part.type === 'cbc' && part.trials.every((trial) => trial.options.length === 3
    && trial.options.every((option) => option.media === 'image' && !option.src.startsWith('ours/post-'))));
  assert.ok(k >= 0, 'the example has a part of three 4:5 stills');
  await page.locator('#menu').click();
  await page.locator('#parts .value').nth(k).getByRole('button', { name: 'Start' }).click();
  if ((await saved(page)).where.startsWith('intro:')) await page.locator('#screen').getByRole('button', { name: 'Start' }).click();
  assert.equal((await saved(page)).where, design.parts[k].trials[0].id);
  await page.waitForFunction(() => [...document.querySelectorAll('#screen .option img')].every((img) => img.dataset.loaded));
  // 540x674: the encoder evens the height.
  const shapes = await page.locator('#screen .option img').evaluateAll((imgs) => imgs.map((img) => img.naturalHeight / img.naturalWidth));
  assert.equal(shapes.length, 3);
  assert.ok(shapes.every((shape) => Math.abs(shape - 1.25) < 0.01), JSON.stringify(shapes));
  assert.equal(await page.locator('#screen .choices.tall').count(), 0);
  assert.deepEqual(problems, []);
  await context.close();
});

// A viewer that can't save shows its warning whole, under the count, at 390 px. The
// warning wraps to three lines in the count's 156 px column, so the footer is taller than the 80 px it keeps
// otherwise. Its limit in this state is 110 px, which a fourth line (20 px more) would break.
test('at 390 px with saving blocked: the warning shows whole and the footer stays within its limit', async () => {
  const LIMIT = 110;
  const { context, page, problems } = await open({ width: 390, height: 844 }, () => {
    Storage.prototype.setItem = () => { throw new DOMException('blocked', 'SecurityError'); };
  });
  assert.equal(await page.locator('#saved').textContent(), 'This viewer can\'t save. Press Save answers before you close it.');
  assert.equal(await page.locator('#saved.ok').count(), 0);
  const layout = await page.evaluate(() => {
    const box = (node) => {
      const { top, bottom, left, right, height } = node.getBoundingClientRect();
      return { top, bottom, left, right, height };
    };
    const state = document.querySelector('.bar .state');
    return { saved: box(document.getElementById('saved')), state: box(state), bar: box(document.querySelector('.bar')),
      cut: state.scrollHeight > state.clientHeight || state.scrollWidth > state.clientWidth, height: innerHeight };
  });
  assert.equal(layout.cut, false, 'the count and warning are cut off');
  for (const outer of [layout.state, layout.bar]) {
    assert.ok(layout.saved.left >= outer.left && layout.saved.right <= outer.right && layout.saved.top >= outer.top
      && layout.saved.bottom <= outer.bottom, `the warning ${JSON.stringify(layout.saved)} outside ${JSON.stringify(outer)}`);
  }
  assert.ok(layout.bar.bottom <= layout.height, 'the footer runs off the screen');
  assert.ok(layout.bar.height <= LIMIT, `the footer is ${layout.bar.height} px`);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0);
  assert.deepEqual(problems, []);
  await context.close();
});

// The range screen names its detail with the same h2.
test('a range trial: the detail is an h2 under the question\'s h1', async () => {
  const { context, page, problems } = await open();
  const k = design.parts.findIndex((part) => part.type === 'range');
  await page.locator('#menu').click();
  await page.locator('#parts .value').nth(k).getByRole('button', { name: 'Start' }).click();
  if ((await saved(page)).where.startsWith('intro:')) await page.locator('#screen').getByRole('button', { name: 'Start' }).click();
  assert.equal(partOf((await saved(page)).where).type, 'range');
  assert.equal(await page.locator('#screen h1').count(), 1);
  assert.equal(await page.locator('#screen h3').count(), 0);
  assert.equal(await page.locator('#screen h2.dimension').count(), 1);
  assert.deepEqual(problems, []);
  await context.close();
});
