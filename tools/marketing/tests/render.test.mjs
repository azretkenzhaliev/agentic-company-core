// The renderer's tests: accented letters in the vetted fonts, PNG sizes, subtitles. Needs the Playwright Chromium
// (npx playwright install chromium); not run in CI.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ffmpeg from 'ffmpeg-static';
import { fontCoverage, renderList, renderPng } from '../render/png.mjs';
import { saveFrames } from '../video/frames.mjs';
import { burnSubtitles } from '../video/subtitles.mjs';
import { ingest } from '../swipe/ingest.mjs';
import { cut } from '../video/cut.mjs';

const tmp = mkdtempSync(join(tmpdir(), 'mkt-render-'));
const template = (name) => fileURLToPath(new URL(`../templates/${name}`, import.meta.url));
const pngSize = (file) => {
  const b = readFileSync(file);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
};

test('both vetted fonts cover ä ö ü ß and are really used', async () => {
  const result = await fontCoverage(['Golos Text', 'Montserrat'], 'ÄÖÜäöüß');
  for (const [family, r] of Object.entries(result)) {
    assert.ok(r.faces > 0, `${family}: no face loaded for ä ö ü ß`);
    assert.ok(r.differsFromFallback, `${family}: renders like the fallback font`);
  }
});

test('templates render at their sizes', async () => {
  for (const [name, size] of [['carousel.html', '1080x1350'], ['news-card.html', '1080x1350'],
    ['quote-card.html', '1080x1350'], ['story.html', '1080x1920']]) {
    const out = join(tmp, name.replace('.html', '.png'));
    await renderPng({ html: template(name), out, size });
    assert.deepEqual(pngSize(out), size.split('x').map(Number), name);
  }
});

test('text in an unvetted font fails the render', async () => {
  const html = join(tmp, 'bad.html');
  writeFileSync(html, "<html><body style=\"font-family: 'Unbounded', serif\"><h1 style=\"font-family:'Unbounded'\">Äöü</h1></body></html>");
  await assert.rejects(renderPng({ html, out: join(tmp, 'bad.png'), size: '1080x1350' }), /fonts/);
});

test('a slide with accented letters renders through renderPng with the vetted fonts', async () => {
  const html = join(tmp, 'de.html');
  writeFileSync(html, "<html><body><h1>Äöü äöü über</h1><p style=\"font-family:'Montserrat'\">Grüße</p><img src='https://example.com/x.png'></body></html>");
  const out = await renderPng({ html, out: join(tmp, 'de.png'), size: '1080x1350' });
  assert.deepEqual(pngSize(out), [1080, 1350]);
});

test('an unknown size is refused', async () => {
  await assert.rejects(renderPng({ html: template('carousel.html'), out: join(tmp, 'x.png'), size: '1920x1080' }), /size/);
});

// List mode: a template that reads window.VALUES, or without it its own file name (as the taste kit's router does).
const listTemplate = (folder) => {
  mkdirSync(folder, { recursive: true });
  const html = join(folder, 'option.html');
  writeFileSync(html, `<!doctype html><html><head><meta charset="utf-8"><script>
document.addEventListener('DOMContentLoaded', () => {
  const v = window.VALUES || { name: decodeURIComponent(location.pathname.split('/').pop()).replace(/\\.html$/, '') };
  document.body.style.background = v.bg || '#202020';
  const h = document.createElement('h1');
  h.textContent = v.name + ' Äöü';
  if (v.font) h.style.fontFamily = v.font;
  document.body.appendChild(h);
});
</script></head><body></body></html>`);
  return html;
};

test('a list renders each entry byte-identical to rendering it alone', async () => {
  const html = listTemplate(join(tmp, 'list-a'));
  const dir = join(tmp, 'list-a/out');
  const alone = join(tmp, 'list-a/alone');
  mkdirSync(dir);
  mkdirSync(alone);
  const list = [{ out: 'one.png', values: { name: 'one', bg: '#103050' } }, { out: 'two.png', values: { name: 'two' } },
    { out: 'three.png', values: { name: 'three', bg: '#503010' } }];
  const { written, failed } = await renderList({ html, list, dir, size: '1080x1080' });
  assert.deepEqual(failed, []);
  assert.deepEqual(written, list.map((e) => join(dir, e.out)));
  for (const e of list) {
    await renderPng({ html, out: join(alone, e.out), size: '1080x1080', values: e.values });
    assert.ok(readFileSync(join(dir, e.out)).equals(readFileSync(join(alone, e.out))), e.out);
    assert.deepEqual(pngSize(join(dir, e.out)), [1080, 1080]);
  }
  const bytes = list.map((e) => readFileSync(join(dir, e.out)).toString('base64'));
  assert.equal(new Set(bytes).size, 3, 'each entry rendered its own values');
});

test('a list entry renders as a copy of the template named for it does, rendered alone without values', async () => {
  const html = listTemplate(join(tmp, 'list-b'));
  const copy = join(tmp, 'list-b/carousel__s1__1.html');
  writeFileSync(copy, readFileSync(html));
  await renderPng({ html: copy, out: join(tmp, 'list-b/copy.png'), size: '1080x1350' });
  const { failed } = await renderList({ html, list: [{ out: 'listed.png', values: { name: 'carousel__s1__1' } }], dir: join(tmp, 'list-b') });
  assert.deepEqual(failed, []);
  assert.ok(readFileSync(join(tmp, 'list-b/listed.png')).equals(readFileSync(join(tmp, 'list-b/copy.png'))));
});

test('a bad list entry fails alone and nothing is written outside the folder', async () => {
  const html = listTemplate(join(tmp, 'list-c'));
  const dir = join(tmp, 'list-c/out');
  mkdirSync(dir);
  const outside = join(tmp, 'list-c/outside.png');
  writeFileSync(outside, 'not to be overwritten');
  symlinkSync(outside, join(dir, 'link.png'));
  const list = [
    { out: 'good-1.png', values: { name: 'a' } },
    { out: '../escape.png' }, { out: 'sub/x.png' }, { out: '/tmp/abs.png' }, { out: '.hidden.png' }, { out: 'x.jpg' }, { out: 'x.png\n' },
    'good-2.png', null, ['x.png'], { out: 'a.png', value: { name: 'typo' } }, { out: 'b.png', values: ['b'] }, { out: 'c.png', values: null },
    { out: 'GOOD-1.png' }, { out: 'link.png' }, { out: 'font.png', values: { name: 'f', font: "'Unbounded'" } },
    { out: 'good-2.png' },
  ];
  const { written, failed } = await renderList({ html, list, dir });
  assert.deepEqual(written, [join(dir, 'good-1.png'), join(dir, 'good-2.png')]);
  assert.deepEqual(failed.map((f) => f.index), [...Array(15).keys()].map((i) => i + 1));
  const reason = (i) => failed.find((f) => f.index === i).error;
  assert.match(reason(1), /plain file name/);
  assert.match(reason(10), /unknown key "value"/);
  assert.match(reason(11), /values is an object/);
  assert.match(reason(13), /repeats/);
  assert.match(reason(14), /link/);
  assert.match(reason(15), /fonts/);
  assert.equal(failed.find((f) => f.index === 15).out, 'font.png');
  assert.equal(failed.find((f) => f.index === 8).out, null);
  assert.equal(readFileSync(outside, 'utf8'), 'not to be overwritten');
  assert.deepEqual(readdirSync(dir).sort(), ['good-1.png', 'good-2.png', 'link.png']);
  assert.deepEqual(readdirSync(join(tmp, 'list-c')).sort(), ['option.html', 'out', 'outside.png']);
});

test('a list call with no entries, no template, no folder or a bad size renders nothing', async () => {
  const html = listTemplate(join(tmp, 'list-d'));
  const dir = join(tmp, 'list-d');
  for (const [args, refusal] of [
    [{ html, list: [], dir }, /non-empty/], [{ html, list: { out: 'a.png' }, dir }, /non-empty/],
    [{ html: join(dir, 'missing.html'), list: [{ out: 'a.png' }], dir }, /template/],
    [{ html, list: [{ out: 'a.png' }], dir: join(dir, 'missing') }, /folder/],
    [{ html, list: [{ out: 'a.png' }], dir: html }, /folder/],
    [{ html, list: [{ out: 'a.png' }], dir, size: '1920x1080' }, /size/],
  ]) {
    await assert.rejects(renderList(args), refusal);
  }
  assert.deepEqual(readdirSync(dir), ['option.html']);
});

test('the list mode on the command line: a summary, each failure, exit 1; a bad call exits 2 in one line', () => {
  const script = fileURLToPath(new URL('../render/png.mjs', import.meta.url));
  const html = listTemplate(join(tmp, 'list-e'));
  const dir = join(tmp, 'list-e');
  const list = join(dir, 'renders.json');
  writeFileSync(list, JSON.stringify([{ out: 'ok.png', values: { name: 'ok' } }, { out: '../no.png' }]));
  const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
  const done = run('--html', html, '--list', list, '--dir', dir);
  assert.equal(done.status, 1, done.stderr);
  assert.match(done.stdout, /wrote 1 of 2 into/);
  assert.match(done.stderr, /failed entry 1 \(\.\.\/no\.png\): out is a plain file name/);
  assert.ok(existsSync(join(dir, 'ok.png')) && !existsSync(join(tmp, 'no.png')));
  writeFileSync(list, JSON.stringify([{ out: 'ok.png', values: { name: 'ok' } }]));
  assert.equal(run('--html', html, '--list', list, '--dir', dir).status, 0);
  assert.equal(run('--html', html, '--list', list, '--dir', dir, '--out', join(dir, 'x.png')).status, 2);
  assert.equal(run('--html', html, '--list', list).status, 2);
  assert.equal(run('--list', list, '--dir', dir).status, 2);
  writeFileSync(join(dir, 'notes.txt'), 'secret-looking words');
  const notJson = run('--html', html, '--list', join(dir, 'notes.txt'), '--dir', dir);
  assert.equal(notJson.status, 2);
  assert.doesNotMatch(notJson.stderr, /secret-looking/);
  assert.equal(run('--html', html, '--list', '', '--dir', dir).status, 2);
  writeFileSync(list, '[]');
  const empty = run('--html', html, '--list', list, '--dir', dir);
  assert.equal(empty.status, 2);
  assert.equal(empty.stderr.trim(), 'the list is a non-empty JSON array of { "out", "values" }');  // one line, no stack
  writeFileSync(list, JSON.stringify([{ out: 'ok.png' }]));
  assert.equal(run('--html', join(dir, 'none.html'), '--list', list, '--dir', dir).status, 2);
  assert.equal(run('--html', html, '--list', list, '--dir', join(dir, 'none')).status, 2);
  assert.equal(run('--html', html, '--list', list, '--dir', dir, '--size', '7x7').status, 2);
});

test('subtitles burn onto a clip without changing its length', () => {
  const clip = join(tmp, 'clip.mp4');
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x202020:s=1080x1920:d=2',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', clip]);
  assert.equal(made.status, 0);
  const srt = join(tmp, 's.srt');
  writeFileSync(srt, '1\n00:00:00,000 --> 00:00:01,500\nÜber uns: äöü\n\n2\n00:00:01,500 --> 00:00:02,000\nIn English\n');
  const out = burnSubtitles({ input: clip, srt, out: join(tmp, 'subbed.mp4') });
  const probe = spawnSync(ffmpeg, ['-hide_banner', '-i', out], { encoding: 'utf8' });  // prints the duration, exits 1
  const [, h, m, sec] = probe.stderr.match(/Duration: (\d+):(\d+):([\d.]+)/);
  const seconds = Number(h) * 3600 + Number(m) * 60 + Number(sec);
  assert.ok(Math.abs(seconds - 2) <= 0.1, `duration ${seconds}`);
});

test('frames default to 540 px wide; --width takes full-resolution stills, a whole number in range', () => {
  const clip = join(tmp, 'tall.mp4');
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=navy:s=1080x1920:d=1:r=1', '-pix_fmt', 'yuv420p', clip]);
  assert.equal(made.status, 0, String(made.stderr));
  saveFrames({ input: clip, out: join(tmp, 'small') });
  saveFrames({ input: clip, out: join(tmp, 'full'), width: 1080 });
  assert.deepEqual(pngSize(join(tmp, 'small/frame-001.png')), [540, 960]);
  assert.deepEqual(pngSize(join(tmp, 'full/frame-001.png')), [1080, 1920]);
  for (const width of [0, -2, 1080.5, 9000, NaN, "540:-2,drawtext=text=x"]) {
    assert.throws(() => saveFrames({ input: clip, out: join(tmp, 'bad'), width }), /width/);
  }
});

test('frames and subtitles read only local files', () => {
  assert.throws(() => saveFrames({ input: 'https://example.com/a.mp4', out: join(tmp, 'f') }), /URL/);
  assert.throws(() => burnSubtitles({ input: 'ftp://example.com/a.mp4', srt: join(tmp, 's.srt'), out: join(tmp, 'x.mp4') }), /URL/);
  assert.throws(() => burnSubtitles({ input: join(tmp, 'clip.mp4'), srt: join(tmp, 's.srt'), out: 'ftp://example.com/x.mp4' }), /URL/);
  // A local playlist: refused by its type before ffmpeg opens it (video/formats.mjs).
  const playlist = join(tmp, 'list.m3u8');
  writeFileSync(playlist, '#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:9/x.ts\n#EXT-X-ENDLIST\n');
  assert.throws(() => saveFrames({ input: playlist, out: join(tmp, 'f') }), /only/);
  assert.throws(() => burnSubtitles({ input: playlist, srt: join(tmp, 's.srt'), out: join(tmp, 'x.mp4') }), /only/);
});

// A repo-like root whose swipe folder is a link to another folder, as it may be to a synced folder.
const repo = join(tmp, 'repo');
const synced = join(tmp, 'synced-swipe');
const swipe = join(repo, 'workspaces/marketing/swipe');
mkdirSync(join(repo, 'workspaces/marketing'), { recursive: true });
mkdirSync(synced);
symlinkSync(synced, swipe);

test('a saved reel is taken apart into frames, scene changes and audio', () => {
  const reel = join(swipe, 'reel.mp4');
  // 2 s: a dark half-second, then a bright one-and-a-half (one scene change), with a tone.
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y',
    '-f', 'lavfi', '-i', 'color=c=black:s=540x960:d=0.5', '-f', 'lavfi', '-i', 'color=c=white:s=540x960:d=1.5',
    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
    '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '2:a',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', reel]);
  assert.equal(made.status, 0);
  const done = ingest({ input: reel, out: join(swipe, 'reel'), root: repo });
  assert.ok(done.frames >= 4 && done.frames <= 5, `frames ${done.frames}`);
  assert.ok(done.scenes >= 1, `scenes ${done.scenes}`);
  assert.ok(done.audio.endsWith('audio.wav'));
  assert.ok(existsSync(join(synced, 'reel/audio.wav')));
});

test('ingest takes only a saved file in the swipe folder and writes only there', () => {
  const saved = join(swipe, 'saved.mp4');
  writeFileSync(saved, 'the paths are checked before ffmpeg runs');
  const outside = join(tmp, 'outside');
  mkdirSync(outside);
  writeFileSync(join(outside, 'reel.mp4'), 'x');
  symlinkSync(outside, join(swipe, 'elsewhere'));  // a link in the swipe folder that points out of it
  for (const [args, refusal] of [
    [{ input: 'https://www.instagram.com/reel/abc/', out: join(swipe, 'a') }, /URL/],
    [{ input: 'ftp://example.com/reel.mp4', out: join(swipe, 'a') }, /URL/],
    [{ input: join(outside, 'reel.mp4'), out: join(swipe, 'a') }, /--in/],
    [{ input: join(swipe, 'elsewhere/reel.mp4'), out: join(swipe, 'a') }, /--in/],
    [{ input: join(swipe, 'missing.mp4'), out: join(swipe, 'a') }, /--in/],
    [{ input: swipe, out: join(swipe, 'a') }, /--in/],
    [{ input: saved, out: join(tmp, 'not-swipe') }, /--out/],
    [{ input: saved, out: join(swipe, '../../../x') }, /--out/],
    [{ input: saved, out: join(swipe, 'elsewhere/x') }, /--out/],
  ]) {
    assert.throws(() => ingest({ ...args, root: repo }), refusal, JSON.stringify(args));
  }
  for (const made of [join(swipe, 'a'), join(tmp, 'not-swipe'), join(repo, 'x'), join(outside, 'x')]) {
    assert.ok(!existsSync(made), `${made} was created`);
  }
});

// fetch.py puts a Board link's video in sources/<brand>/<week>/<slug>/ with its manifest.
const sources = join(repo, 'workspaces/marketing/sources');

test('ingest also takes a downloaded reel from sources/, writes only into swipe/ and keeps the video', () => {
  const folder = join(sources, 'founder/demo/2026-W05/board-link');
  mkdirSync(folder, { recursive: true });
  const video = join(folder, 'video.mp4');
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=540x960:d=1',
    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video]);
  assert.equal(made.status, 0);
  const done = ingest({ input: video, out: join(swipe, 'board-link'), root: repo });
  assert.ok(done.frames >= 2, `frames ${done.frames}`);
  assert.ok(existsSync(join(synced, 'board-link/audio.wav')));
  assert.ok(existsSync(video), 'the video is kept for compilations');
  assert.deepEqual(readdirSync(folder), ['video.mp4'], 'nothing written beside the download');
});

test('ingest refuses a sources/ path that leads out, and any --out outside swipe/', () => {
  const kept = join(sources, 'founder/demo/2026-W05/kept/video.mp4');
  mkdirSync(join(kept, '..'), { recursive: true });
  writeFileSync(kept, 'the paths are checked before ffmpeg runs');
  const outside = join(tmp, 'outside-sources');
  mkdirSync(outside);
  writeFileSync(join(outside, 'reel.mp4'), 'x');
  symlinkSync(outside, join(sources, 'elsewhere'));
  mkdirSync(join(repo, 'workspaces/marketing/inbox'));
  writeFileSync(join(repo, 'workspaces/marketing/inbox/reel.mp4'), 'x');  // a real file beside sources/, not in it
  for (const [args, refusal] of [
    [{ input: join(sources, 'elsewhere/reel.mp4'), out: join(swipe, 'b') }, /--in/],
    [{ input: join(sources, '../inbox/reel.mp4'), out: join(swipe, 'b') }, /--in/],
    [{ input: kept, out: join(sources, 'founder/demo/2026-W05/kept/frames') }, /--out/],
    [{ input: kept, out: join(sources, 'elsewhere/frames') }, /--out/],
  ]) {
    assert.throws(() => ingest({ ...args, root: repo }), refusal, JSON.stringify(args));
  }
  for (const made of [join(swipe, 'b'), join(sources, 'founder/demo/2026-W05/kept/frames'), join(outside, 'frames')]) {
    assert.ok(!existsSync(made), `${made} was created`);
  }
});

test('the Arabic font covers Arabic only, not Latin', async () => {
  const arabic = await fontCoverage(['Scheherazade New'], 'العلم نور');
  assert.ok(arabic['Scheherazade New'].faces > 0);
  assert.ok(arabic['Scheherazade New'].differsFromFallback);
  // The Arabic subset has no Latin glyphs, so Latin text falls through to the next font in the stack.
  const latin = await fontCoverage(['Scheherazade New'], 'Hello World 123');
  assert.equal(latin['Scheherazade New'].differsFromFallback, false);
});

test('cut.mjs cuts a clip into media and refuses anything else', () => {
  const root = mkdtempSync(join(tmpdir(), 'mkt-cut-'));
  for (const f of ['workspaces/marketing/inbox', 'workspaces/marketing/media/a']) mkdirSync(join(root, f), { recursive: true });
  const clip = join(root, 'workspaces/marketing/inbox/clip.mp4');
  const made = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:d=3',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', clip]);
  assert.equal(made.status, 0);
  const out = cut({ input: clip, out: join(root, 'workspaces/marketing/media/a/cut.mp4'), start: '1', duration: '1', root });
  assert.ok(out.endsWith('cut.mp4'));
  for (const bad of [
    { input: 'https://x.test/a.mp4', out: join(root, 'workspaces/marketing/media/a/b.mp4') },
    { input: clip, out: 'file:/tmp/x.mp4' },
    { input: clip, out: join(root, 'outside.mp4') },
    { input: clip, out: join(root, 'workspaces/marketing/media/a/cut.mp4') },  // exists
    { input: '/etc/hosts', out: join(root, 'workspaces/marketing/media/a/c.mp4') },
  ]) assert.throws(() => cut({ ...bad, start: '0', duration: '1', root }), /refused/);
});
