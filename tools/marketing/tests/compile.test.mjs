// Tests for video/compile.mjs on synthetic clips made here with the bundled ffmpeg: the reel's size, rate and
// length, pause cuts, subtitle timing, provenance and manifests, and hostile edit lists.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test, { after } from 'node:test';
import ffmpeg from 'ffmpeg-static';
import { applyVars, batch, compile, formatSrt, main, parseSrt, proposeCuts, readVars, remapCues, segments, silences, wrote } from '../video/compile.mjs';

const root = mkdtempSync(join(tmpdir(), 'mkt-compile-test-'));
after(() => rmSync(root, { recursive: true, force: true }));
const M = (p) => join('workspaces/marketing', p);
for (const d of ['inbox', 'media/b/w/p', 'sources/b/w/clip', 'sources/b/w/song', 'sources/b/w/beep', 'sources/b/w/open', 'sources/b/w/none']) mkdirSync(join(root, M(d)), { recursive: true });
const make = (rel, lavfi) => {
  const run = spawnSync(ffmpeg, ['-loglevel', 'error', '-y', ...lavfi, join(root, rel)]);
  assert.equal(run.status, 0, String(run.stderr));
  return rel;
};
const sha = (rel) => createHash('sha256').update(readFileSync(join(root, rel))).digest('hex');
const info = (rel) => spawnSync(ffmpeg, ['-hide_banner', '-i', join(root, rel)], { encoding: 'utf8' }).stderr;
const seconds = (rel) => {
  const [, h, m, s] = info(rel).match(/Duration: (\d+):(\d+):([\d.]+)/);
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
};

// His clip: 4 s, landscape, a tone with a pause from 1.5 s to 2.7 s.
const own = make(M('inbox/take.mp4'), ['-f', 'lavfi', '-i', 'testsrc=s=640x360:d=4:r=25', '-f', 'lavfi', '-i',
  "aevalsrc=if(between(t\\,1.5\\,2.7)\\,0\\,0.5*sin(440*2*PI*t)):d=4:s=48000", '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac']);
// Outside footage, with no sound, and its manifest.
const outside = make(M('sources/b/w/clip/video.mp4'), ['-f', 'lavfi', '-i', 'color=c=navy:s=1920x1080:d=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p']);
const song = make(M('sources/b/w/song/song.m4a'), ['-f', 'lavfi', '-i', 'sine=f=220:d=2', '-c:a', 'aac']);
const voice = make(M('media/b/w/p/voice.m4a'), ['-f', 'lavfi', '-i', 'sine=f=660:d=2', '-c:a', 'aac']);
const overlay = make(M('media/b/w/p/title.png'), ['-f', 'lavfi', '-i', 'color=c=0x0dc8b1:s=1080x400,format=rgba', '-frames:v', '1']);
const broll = make(M('media/b/w/p/broll.mp4'), ['-f', 'lavfi', '-i', 'color=c=green:s=1080x1920:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p']);
writeFileSync(join(root, `${broll}.json`), JSON.stringify({ prompt: 'a calm green field', ai_generated: true }));
const beep = make(M('media/b/w/p/beep.m4a'), ['-f', 'lavfi', '-i', 'sine=f=880:d=0.5', '-c:a', 'aac']);
const outsideBeep = make(M('sources/b/w/beep/video.mp3'), ['-f', 'lavfi', '-i', 'sine=f=1320:d=0.5']);
// A still with one white band high up, for the zoom.
const bands = make(M('media/b/w/p/bands.png'), ['-f', 'lavfi', '-i', 'color=c=black:s=1080x1920,drawbox=x=0:y=100:w=1080:h=200:color=white:t=fill', '-frames:v', '1']);
// A grey still, for warmth; stills in four colours by quadrant (red, lime / blue, white), for the corner crop.
const grey = make(M('media/b/w/p/grey.png'), ['-f', 'lavfi', '-i', 'color=c=0x808080:s=1080x1920', '-frames:v', '1']);
const quadrants = (name, w, h) => make(M(`media/b/w/p/${name}.png`), ['-f', 'lavfi', '-i', `color=c=red:s=${w}x${h},`
  + `drawbox=x=${w / 2}:y=0:w=${w / 2}:h=${h / 2}:color=lime:t=fill,drawbox=x=0:y=${h / 2}:w=${w / 2}:h=${h / 2}:color=blue:t=fill,`
  + `drawbox=x=${w / 2}:y=${h / 2}:w=${w / 2}:h=${h / 2}:color=white:t=fill`, '-frames:v', '1']);
const wide = quadrants('wide', 1920, 1080), tall = quadrants('tall', 1080, 1920);
// Hits with tall peaks over a quiet tone: turned up to -14 LUFS, only a limiter keeps the peaks under -1 dBTP.
const drums = make(M('media/b/w/p/drums.m4a'), ['-f', 'lavfi', '-i', 'aevalsrc=0.9*exp(-30*mod(t\\,0.5))*sin(2*PI*80*t)+0.05*sin(2*PI*440*t):d=3:s=48000', '-c:a', 'aac']);
const manifest = (rel, extra = {}) => writeFileSync(join(root, rel.replace(/[^/]+$/, 'MANIFEST.json')), JSON.stringify({ files: [{
  file: rel.split('/').pop(), sha256: sha(rel), source_url: 'https://example.test/v/1', owner: 'Example', licence: null, ...extra }] }));
manifest(outside);
manifest(song, { licence: 'example licence', music_ok: true });
manifest(outsideBeep, { licence: 'CC0 1.0', music_ok: true });
// The video stream's own frame count: the file's length can come from its audio alone.
const videoFrames = (rel) => Number(spawnSync(ffmpeg, ['-hide_banner', '-i', join(root, rel), '-map', '0:v', '-c', 'copy', '-f', 'null', '-'],
  { encoding: 'utf8' }).stderr.match(/frame=\s*(\d+)/g).pop().match(/\d+/)[0]);
// One pixel's colour at time t, and an audio band's loudness over [from, to), from the rendered reel.
const pixel = (rel, t, x, y) => [...spawnSync(ffmpeg, ['-loglevel', 'error', '-ss', String(t), '-i', join(root, rel), '-frames:v', '1',
  '-vf', `crop=2:2:${x}:${y}`, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 20 }).stdout].slice(0, 3);  // 2x2: 4:2:0 chroma
const level = (rel, from, to, hz) => Number(spawnSync(ffmpeg, ['-hide_banner', '-ss', String(from), '-t', String(to - from), '-i', join(root, rel),
  '-af', `bandpass=f=${hz}:width_type=q:w=8,volumedetect`, '-f', 'null', '-'], { encoding: 'utf8' }).stderr.match(/mean_volume: (-?[\d.]+)/)[1]);
const teal = (rgb) => Math.abs(rgb[0] - 13) < 30 && Math.abs(rgb[1] - 200) < 30 && Math.abs(rgb[2] - 177) < 30;
const near = (rgb, want) => rgb.every((c, i) => Math.abs(c - want[i]) < 60);
// The sound's integrated loudness (LUFS) and true peak (dBTP) by EBU R128, measured here, not by compile.mjs.
const loud = (rel) => {
  const summary = spawnSync(ffmpeg, ['-hide_banner', '-nostats', '-i', join(root, rel), '-map', '0:a:0', '-af', 'ebur128=peak=true:framelog=verbose',
    '-f', 'null', '-'], { encoding: 'utf8' }).stderr.split('Summary:').pop();
  const db = (re) => { const v = summary.match(re)[1]; return v === '-inf' ? -Infinity : Number(v); };
  return { lufs: db(/I:\s+(-?[\d.]+|-inf) LUFS/), peak: db(/Peak:\s+(-?[\d.]+|-inf) dBFS/) };
};
// The decoded picture's checksum: the same frames, whatever the container or the sound.
const picture = (rel) => spawnSync(ffmpeg, ['-loglevel', 'error', '-i', join(root, rel), '-map', '0:v:0', '-f', 'md5', '-'], { encoding: 'utf8' }).stdout.trim();
writeFileSync(join(root, M('inbox/take.srt')), '1\n00:00:00,500 --> 00:00:01,400\nErstes Wort\n\n2\n00:00:02,000 --> 00:00:02,500\nPause\n\n'
  + '3\n00:00:03,000 --> 00:00:03,800\nLetztes Wort\n');

test('segments: cuts split a clip; nothing left or too long is refused', () => {
  assert.deepEqual(segments([{ in: 0, out: 4 }], [{ clip: 0, from: 1.6, to: 2.6 }]).map((p) => [p.from, p.to, p.at]),
    [[0, 1.6, 0], [2.6, 4, 1.6]]);
  assert.throws(() => segments([{ in: 1, out: 2 }], [{ clip: 0, from: 0, to: 3 }]), /nothing left/);
  assert.throws(() => segments([{ in: 0, out: 1000 }]), /at most/);
  assert.throws(() => segments([{ in: 3, out: 2 }]), /in < out/);
});

test('subtitles follow the cuts: cut words drop, later ones move up', () => {
  const parts = segments([{ in: 0, out: 4 }], [{ clip: 0, from: 1.6, to: 2.6 }]);
  const cues = remapCues(parseSrt(readFileSync(join(root, M('inbox/take.srt')), 'utf8')), parts);
  assert.deepEqual(cues.map((c) => [c.text, +c.start.toFixed(2), +c.end.toFixed(2)]),
    [['Erstes Wort', 0.5, 1.4], ['Letztes Wort', 2, 2.8]]);
  assert.match(formatSrt(cues), /00:00:02,000 --> 00:00:02,800\nLetztes Wort/);
});

test('pauses are proposed as cuts in the clip\'s own time', () => {
  const { cuts } = proposeCuts({ clips: [{ file: own, in: 0, out: 4 }] }, { root });
  assert.equal(cuts.length, 1, JSON.stringify(cuts));
  assert.ok(cuts[0].from > 1.5 && cuts[0].from < 1.8 && cuts[0].to > 2.4 && cuts[0].to < 2.7, JSON.stringify(cuts));
});

test('a full compile: 1080x1920 at 30 fps, the right length, provenance and the manifest', () => {
  const list = {
    clips: [{ file: own, in: 0, out: 4, srt: M('inbox/take.srt') }, { file: outside, in: 0.5, out: 2 }, { file: broll, in: 0, out: 1 }],
    cuts: [{ clip: 0, from: 1.6, to: 2.6 }],
    overlays: [{ file: overlay, start: 0.2, end: 1.5, y: 250 }],
    voice: { file: voice, start: 3 },
    music: { file: song, volume: 0.2 },
  };
  const { out, record } = compile(list, join(root, M('media/b/w/p/reel.mp4')), { root });
  const probe = info(M('media/b/w/p/reel.mp4'));
  assert.match(probe, /1080x1920/);
  assert.match(probe, /30 fps/);
  assert.match(probe, /Audio: aac/);
  assert.ok(Math.abs(seconds(M('media/b/w/p/reel.mp4')) - 5.5) < 0.15, `length ${seconds(M('media/b/w/p/reel.mp4'))}`);
  assert.equal(record.seconds, 5.5);
  assert.equal(record.ai_generated, true);  // the b-roll's sidecar
  const kinds = Object.fromEntries(record.inputs.map((i) => [i.file, i.provenance]));
  assert.deepEqual(kinds, { [own]: 'own-footage', [outside]: 'outside', [broll]: 'ai-generated', [overlay]: 'own-render',
    [voice]: 'own-render', [song]: 'outside' });
  assert.equal(record.inputs.find((i) => i.file === outside).sha256, sha(outside));
  assert.equal(record.subtitles, 2);
  assert.deepEqual(JSON.parse(readFileSync(`${out}.json`, 'utf8')).parts.length, 4);
  const entry = JSON.parse(readFileSync(join(root, M('sources/b/w/clip/MANIFEST.json')), 'utf8')).files[0];
  assert.deepEqual(entry.used.map((u) => [u.from, u.to]), [[0.5, 2]]);
});

test('a crossfade overlaps a clip with the one before it; a clip with nothing before it, or too short, is refused', () => {
  const parts = segments([{ in: 0, out: 2 }, { in: 0, out: 2, crossfade: 0.5 }, { in: 0, out: 2, crossfade: 0.25 }]);
  assert.deepEqual(parts.map((p) => [p.at, p.fade]), [[0, 0], [1.5, 0.5], [3.25, 0.25]]);
  // Only a clip's first kept part fades in; cuts inside it stay hard.
  assert.deepEqual(segments([{ in: 0, out: 2 }, { in: 0, out: 4, crossfade: 0.5 }], [{ clip: 1, from: 2, to: 3 }]).map((p) => [p.at, p.fade]),
    [[0, 0], [1.5, 0.5], [3.5, 0]]);
  const cues = remapCues([{ start: 0.5, end: 1, text: 'x' }], parts.filter((p) => p.clip === 1));
  assert.deepEqual(cues.map((c) => [c.start, c.end]), [[2, 2.5]]);  // subtitles land where the clip now plays
  assert.throws(() => segments([{ in: 0, out: 2, crossfade: 0.5 }]), /crossfade/);
  assert.throws(() => segments([{ in: 0, out: 2 }, { in: 0, out: 2, crossfade: -1 }]), /crossfade/);
  assert.throws(() => segments([{ in: 0, out: 2 }, { in: 0, out: 2, crossfade: 0.05 }]), /at least 0.1 s/);
  assert.equal(segments([{ in: 0, out: 2 }, { in: 0, out: 2, crossfade: 0 }])[1].at, 2);  // 0 is no crossfade
  assert.throws(() => segments([{ in: 0, out: 2 }, { in: 0, out: 2, crossfade: 'x' }]), /must be a number/);
  assert.throws(() => segments([{ in: 0, out: 1 }, { in: 0, out: 2, crossfade: 1 }]), /too short/);
  assert.throws(() => segments([{ in: 0, out: 2 }, { in: 0, out: 1, crossfade: 0.6 }, { in: 0, out: 2, crossfade: 0.6 }]), /too short/);
});

test('crossfades shorten the reel by their length, across hard cuts and in a chain', () => {
  const rel = M('media/b/w/p/fades.mp4');
  const { record } = compile({ clips: [{ file: own, in: 0, out: 4 }, { file: outside, in: 0, out: 3, crossfade: 1 }, { file: broll, in: 0, out: 2, crossfade: 0.5 }],
    cuts: [{ clip: 0, from: 1.6, to: 2.6 }] }, join(root, rel), { root });
  assert.equal(record.seconds, 3 + 3 + 2 - 1.5);
  assert.ok(Math.abs(seconds(rel) - 6.5) < 0.15, `length ${seconds(rel)}`);
  assert.deepEqual(record.parts.map((p) => p.at), [0, 1.6, 2, 4.5]);
  assert.ok(pixel(rel, 3.5, 540, 960)[2] > 80, 'the navy clip plays after the first fade');
  assert.ok(pixel(rel, 6, 540, 960)[1] > 100, 'the green clip ends the reel');
  // His tone runs to the end of his clip, fades over 2-3 s, and the navy clip has no sound.
  assert.ok(level(rel, 0.2, 1.4, 440) - level(rel, 3.1, 4.1, 440) > 20, 'the sound crossfades too');
});

test('a crossfade dissolves: halfway through, both clips show', () => {
  const rel = M('media/b/w/p/dissolve.mp4');
  compile({ clips: [{ file: outside, in: 0, out: 3 }, { file: broll, in: 0, out: 2, crossfade: 1 }] }, join(root, rel), { root });
  const [before, during, after] = [pixel(rel, 1, 540, 960), pixel(rel, 2.5, 540, 960), pixel(rel, 3.5, 540, 960)];
  assert.ok(during[2] < before[2] - 20 && during[2] > after[2] + 20, `blue falls: ${before} ${during} ${after}`);
  assert.ok(during[1] > before[1] + 20 && during[1] < after[1] - 20, `green rises: ${before} ${during} ${after}`);
});

test('a clip that runs out before its crossfade ends keeps the rest of the picture', () => {
  // "out" may sit 0.05 s past a clip's last frame, so the first stream stops short of the fade's end.
  const rel = M('media/b/w/p/short.mp4');
  const { record } = compile({ clips: [{ file: outside, in: 0, out: 3.04 }, { file: broll, in: 0, out: 2, crossfade: 0.1 }] }, join(root, rel), { root });
  assert.ok(Math.abs(videoFrames(rel) - record.seconds * 30) <= 2, `${videoFrames(rel)} video frames for ${record.seconds} s`);
  assert.ok(pixel(rel, 4.5, 540, 960)[1] > 100, 'the second clip still ends the reel');
  assert.ok(pixel(rel, 3, 540, 960)[2] > 25, `its last frame holds under the fade, no black: ${pixel(rel, 3, 540, 960)}`);
});

test('a still after a crossfade is shown, for its whole length, at the end of a chain', () => {
  // A still has its frames ready before the clip ahead of it has played; ffmpeg's xfade ended the picture there.
  const rel = M('media/b/w/p/still-last.mp4');
  const { record } = compile({ clips: [{ file: outside, in: 0, out: 3 }, { file: broll, in: 0, out: 2, crossfade: 0.5 }, { file: bands, in: 0, out: 2, crossfade: 0.5 }] },
    join(root, rel), { root });
  assert.equal(record.seconds, 6);
  assert.equal(videoFrames(rel), 180);
  assert.ok(pixel(rel, 5.9, 540, 200).every((c) => c > 200), `the band at the end: ${pixel(rel, 5.9, 540, 200)}`);
  assert.ok(pixel(rel, 5.9, 540, 960).every((c) => c < 40), `black under it: ${pixel(rel, 5.9, 540, 960)}`);
});

test('sound effects play at their start, over the voice and past the music, and count as inputs', () => {
  const rel = M('media/b/w/p/sfx.mp4');
  const { record } = compile({ clips: [{ file: broll, in: 0, out: 2 }, { file: outside, in: 0, out: 3 }],
    sfx: [{ file: beep, start: 1.5, volume: 0.8 }, { file: outsideBeep, start: 3.5 }], music: { file: song, volume: 0.5 } }, join(root, rel), { root });
  assert.ok(level(rel, 1.55, 1.95, 880) - level(rel, 0.5, 1.4, 880) > 20, 'our effect plays at 1.5 s');
  assert.ok(level(rel, 3.55, 3.95, 1320) - level(rel, 2.2, 3.4, 1320) > 20, 'the outside effect plays at 3.5 s');
  assert.ok(Math.abs(level(rel, 1.6, 1.95, 220) - level(rel, 0.5, 1.4, 220)) < 3, 'effects do not duck the music');
  const inputs = Object.fromEntries(record.inputs.map((i) => [i.file, i]));
  assert.equal(inputs[beep].provenance, 'own-render');
  assert.deepEqual([inputs[outsideBeep].provenance, inputs[outsideBeep].licence, inputs[outsideBeep].sha256], ['outside', 'CC0 1.0', sha(outsideBeep)]);
});

test('sfx is no way round "music_ok": an outside sound needs it, whatever its licence or length', () => {
  const clips = [{ file: outside, in: 0, out: 3 }];
  const open = make(M('sources/b/w/open/open.mp3'), ['-f', 'lavfi', '-i', 'sine=f=500:d=1']);
  const unlicensed = make(M('sources/b/w/none/none.mp3'), ['-f', 'lavfi', '-i', 'sine=f=500:d=1']);
  manifest(open, { licence: 'CC0 1.0' });
  manifest(unlicensed);
  const bad = [
    [[{ file: open }], /music_ok/],
    [[{ file: unlicensed }], /music_ok/],
    [[0, 1, 2].map((start) => ({ file: open, start })), /music_ok/],  // short effects chained into a bed
    [[{ file: open, music_ok: true }], /music_ok/],  // the list can't grant itself what the manifest says
    [[{ file: open, licence: 'CC0 1.0', provenance: 'own-render' }], /music_ok/],
    [[{ file: overlay }], /no sound/],
    [[{ file: broll }], /no sound/],  // a video with no sound
    [[{ file: beep, start: 3 }], /inside the reel/],
    [[{ file: beep, start: -0.5 }], /inside the reel/],
    [[{ file: 'file:/etc/hosts' }], /URL|protocol/],
    [[{ file: beep, volume: 'x; rm' }], /must be a number/],
  ];
  bad.forEach(([sfx, why], i) => assert.throws(() => compile({ clips, sfx }, join(root, M(`media/b/w/p/badsfx-${i}.mp4`)), { root }), why));
});

test('a zoom pushes the footage in and back, under our overlays and subtitles', () => {
  const rel = M('media/b/w/p/zoom.mp4');
  compile({ clips: [{ file: bands, in: 0, out: 3 }], zooms: [{ start: 1, end: 2, scale: 1.5 }],
    overlays: [{ file: overlay, start: 0, end: 3, y: 1400 }] }, join(root, rel), { root });
  const white = (rgb) => rgb.every((c) => c > 200);
  assert.ok(white(pixel(rel, 0.5, 540, 200)), `the band before the zoom: ${pixel(rel, 0.5, 540, 200)}`);
  assert.ok(!white(pixel(rel, 1.5, 540, 200)), `pushed off the frame at the peak: ${pixel(rel, 1.5, 540, 200)}`);
  assert.ok(white(pixel(rel, 2.5, 540, 200)), `back after the zoom: ${pixel(rel, 2.5, 540, 200)}`);
  assert.ok(teal(pixel(rel, 1.5, 540, 1600)), `the overlay holds still: ${pixel(rel, 1.5, 540, 1600)}`);
  assert.ok(Math.abs(seconds(rel) - 3) < 0.15, `length ${seconds(rel)}`);
});

test('a grade changes the footage, not our overlays', () => {
  const rel = M('media/b/w/p/grade.mp4');
  compile({ clips: [{ file: outside, in: 0, out: 2 }], grade: { saturation: 0, contrast: 1.1 }, overlays: [{ file: overlay, start: 0, end: 2, y: 250 }] }, join(root, rel), { root });
  const rgb = pixel(rel, 1, 540, 1500);
  assert.ok(Math.max(...rgb) - Math.min(...rgb) < 12, `navy turned grey: ${rgb}`);
  assert.ok(teal(pixel(rel, 1, 540, 450)), `the overlay keeps its colour: ${pixel(rel, 1, 540, 450)}`);
});

test('zooms and grades take numbers in range, nothing else', () => {
  const clips = [{ file: outside, in: 0, out: 1 }];
  const bad = [
    [{ zooms: [{ start: 0, end: 1, scale: 1 }] }, /scale/],
    [{ zooms: [{ start: 0, end: 1, scale: 2.5 }] }, /scale/],
    [{ zooms: [{ start: 1, end: 1, scale: 1.1 }] }, /start < end/],
    [{ zooms: [{ start: -1, end: 1, scale: 1.1 }] }, /start < end/],
    [{ zooms: [{ start: 0, end: 1, scale: "1.1'[x]" }] }, /must be a number/],
    [{ grade: { hue: 10 } }, /grade/],
    [{ grade: JSON.parse('{"toString": 1}') }, /grade has only/],
    [{ grade: { contrast: 9 } }, /grade/],
    [{ grade: { saturation: "1:gamma=2'" } }, /must be a number/],
    [{ grade: 'warm' }, /grade/],
    [{ grade: { warmth: 2 } }, /grade\.warmth must be -1 to 1/],
    [{ grade: { warmth: 'warm' } }, /grade\.warmth must be a number/],
    [{ zooms: [{ start: 0, end: 1, scale: 1.1, ease: 'cubic' }] }, /ease must be sine or linear/],
    [{ zooms: [{ start: 0, end: 1, scale: 1.1, ease: null }] }, /ease must be sine or linear/],
    [{ clips: [{ ...clips[0], crop: 'top-left' }] }, /crop must be an object/],
    [{ clips: [{ ...clips[0], crop: { corner: 'middle', size: 0.8 } }] }, /crop\.corner must be/],
    [{ clips: [{ ...clips[0], crop: { corner: 'top-left', size: 0.4 } }] }, /crop\.size must be 0\.5 to 1/],
    [{ clips: [{ ...clips[0], crop: { corner: 'top-left', size: 1.2 } }] }, /crop\.size must be 0\.5 to 1/],
    [{ clips: [{ ...clips[0], crop: { corner: 'top-left', size: "0.8'[x]" } }] }, /crop\.size must be a number/],
    [{ clips: [{ ...clips[0], crop: { corner: 'top-left' } }] }, /crop\.size must be a number/],
    [{ clips: [{ ...clips[0], crop: { corner: 'top-left', size: 0.8, x: 10 } }] }, /crop has only corner and size/],
    [{ loudness: 'yes' }, /loudness must be true or false/],
  ];
  bad.forEach(([extra, why], i) => assert.throws(() => compile({ clips, ...extra }, join(root, M(`media/b/w/p/badlook-${i}.mp4`)), { root }), why));
});

test('warmth warms or cools the footage, not our overlays; 0 changes nothing', () => {
  const reel = (name, grade) => {
    compile({ clips: [{ file: grey, in: 0, out: 1 }], ...(grade && { grade }), overlays: [{ file: overlay, start: 0, end: 1, y: 250 }] },
      join(root, M(`media/b/w/p/${name}.mp4`)), { root });
    return M(`media/b/w/p/${name}.mp4`);
  };
  const [plain, warm, cool, zero] = [reel('warmth-none'), reel('warmth-1', { warmth: 1 }), reel('warmth-cool', { warmth: -1 }), reel('warmth-0', { warmth: 0 })];
  const [r, , b] = pixel(warm, 0.5, 540, 1500);
  assert.ok(r - b > 20, `warmer: red over blue, ${pixel(warm, 0.5, 540, 1500)}`);
  const [r2, , b2] = pixel(cool, 0.5, 540, 1500);
  assert.ok(b2 - r2 > 10, `cooler: blue over red, ${pixel(cool, 0.5, 540, 1500)}`);
  const [r0, , b0] = pixel(plain, 0.5, 540, 1500);
  assert.ok(Math.abs(r0 - b0) < 6, `no grade stays grey: ${pixel(plain, 0.5, 540, 1500)}`);
  assert.ok(teal(pixel(warm, 0.5, 540, 450)), `the overlay keeps its colour: ${pixel(warm, 0.5, 540, 450)}`);
  assert.equal(picture(zero), picture(plain), 'warmth 0 is no grade');
  assert.match(info(warm), /yuv420p\(tv, bt709, /, 'a warm reel keeps its colour tags');
});

test('a linear push goes in at an even speed and is at its scale at the end; the default eases as a sine', () => {
  const reel = (name, zoom) => {
    compile({ clips: [{ file: bands, in: 0, out: 3 }], zooms: [{ start: 1, end: 2, scale: 1.5, ...zoom }] }, join(root, M(`media/b/w/p/${name}.mp4`)), { root });
    return M(`media/b/w/p/${name}.mp4`);
  };
  const [linear, sine, plain] = [reel('push-linear', { ease: 'linear' }), reel('push-sine', { ease: 'sine' }), reel('push-default', {})];
  const white = (rel, t) => pixel(rel, t, 540, 200).every((c) => c > 200);
  // The band at y 200 leaves the frame once the push passes about 1.15x.
  assert.ok(white(linear, 0.5), 'the band before the push');
  assert.ok(white(linear, 1.2), 'a fifth of the way in, an even push is still under 1.15x');
  assert.ok(!white(sine, 1.2), 'a sine is past it by then');
  assert.ok(!white(linear, 1.95), 'near the end, a linear push is near its scale');
  assert.ok(white(sine, 1.95), 'a sine is nearly back by then');
  assert.ok(white(linear, 2.5), 'back after the push');
  assert.equal(picture(plain), picture(sine), 'the default is the sine');
});

test('a corner crop shows that corner of the clip, wide or tall', () => {
  const corners = { 'top-left': [255, 0, 0], 'top-right': [0, 255, 0], 'bottom-left': [0, 0, 255], 'bottom-right': [255, 255, 255] };
  for (const [corner, rgb] of Object.entries(corners)) {
    const rel = M(`media/b/w/p/crop-${corner}.mp4`);
    compile({ clips: [{ file: wide, in: 0, out: 1, crop: { corner, size: 0.5 } }], overlays: [{ file: overlay, start: 0, end: 1, y: 250 }] }, join(root, rel), { root });
    for (const [x, y] of [[20, 20], [540, 1500], [1056, 1896]]) assert.ok(near(pixel(rel, 0.5, x, y), rgb), `${corner} at ${x},${y}: ${pixel(rel, 0.5, x, y)}`);
    assert.ok(teal(pixel(rel, 0.5, 540, 450)), `the overlay isn't cropped: ${pixel(rel, 0.5, 540, 450)}`);
  }
  // A tall clip at size 0.5: its bottom-right quarter fills the frame; at size 1, the whole of it, as with no crop.
  const quarter = M('media/b/w/p/crop-tall.mp4'), whole = M('media/b/w/p/crop-tall-1.mp4'), none = M('media/b/w/p/crop-none.mp4');
  compile({ clips: [{ file: tall, in: 0, out: 1, crop: { corner: 'bottom-right', size: 0.5 } }] }, join(root, quarter), { root });
  for (const [x, y] of [[20, 20], [1056, 1896]]) assert.ok(near(pixel(quarter, 0.5, x, y), [255, 255, 255]), `tall at ${x},${y}: ${pixel(quarter, 0.5, x, y)}`);
  compile({ clips: [{ file: tall, in: 0, out: 1, crop: { corner: 'top-left', size: 1 } }] }, join(root, whole), { root });
  compile({ clips: [{ file: tall, in: 0, out: 1 }] }, join(root, none), { root });
  assert.equal(picture(whole), picture(none));
});

test('the sound is mastered to -14 LUFS with true peaks at most -1 dBTP, from quiet, hot or peaky', () => {
  const reels = {
    quiet: { clips: [{ file: own, in: 0, out: 4, volume: 0.1 }] },
    hot: { clips: [{ file: own, in: 0, out: 4, volume: 2 }] },
    peaky: { clips: [{ file: outside, in: 0, out: 3 }], sfx: [{ file: drums, start: 0 }] },
  };
  for (const [name, list] of Object.entries(reels)) {
    const rel = M(`media/b/w/p/loud-${name}.mp4`);
    const { record } = compile(list, join(root, rel), { root });
    const { lufs, peak } = loud(rel);
    assert.ok(Math.abs(lufs + 14) <= 0.5, `${name}: ${lufs} LUFS`);
    assert.ok(peak <= -1.0, `${name}: true peak ${peak} dBTP`);
    assert.ok(Math.abs(record.loudness.lufs - lufs) < 0.05 && Math.abs(record.loudness.true_peak - peak) < 0.05, `${name}: the record ${JSON.stringify(record.loudness)}`);
    assert.match(info(rel), /yuv420p\(tv, bt709, /, `${name}: the picture keeps its colour tags`);
    assert.ok(Math.abs(seconds(rel) - (name === 'peaky' ? 3 : 4)) < 0.15, `${name}: length ${seconds(rel)}`);
  }
  const before = (name) => JSON.parse(readFileSync(join(root, M(`media/b/w/p/loud-${name}.mp4.json`)), 'utf8')).loudness.before;
  assert.ok(before('quiet').lufs < -20 && before('hot').lufs > -8, `before: ${JSON.stringify([before('quiet'), before('hot')])}`);
  assert.ok(before('peaky').true_peak + (-14 - before('peaky').lufs) > 0, `the drums' peaks would clip without the limiter: ${JSON.stringify(before('peaky'))}`);
});

test('a silent reel is left silent, and loudness false leaves the sound as it is', () => {
  const silent = M('media/b/w/p/loud-silent.mp4');
  const { record } = compile({ clips: [{ file: outside, in: 0, out: 2 }] }, join(root, silent), { root });
  assert.equal(record.loudness.silent, true);
  assert.ok(loud(silent).lufs <= -60, `still silent: ${JSON.stringify(loud(silent))}`);
  const off = M('media/b/w/p/loud-off.mp4'), on = M('media/b/w/p/loud-on.mp4');
  const quiet = { clips: [{ file: own, in: 0, out: 4, volume: 0.1 }] };
  const { record: unmastered } = compile({ ...quiet, loudness: false }, join(root, off), { root });
  const { record: mastered } = compile({ ...quiet, loudness: true }, join(root, on), { root });
  assert.equal(unmastered.loudness.off, true);
  assert.ok(Math.abs(loud(off).lufs - mastered.loudness.before.lufs) < 0.5, `as it was: ${loud(off).lufs} vs ${mastered.loudness.before.lufs}`);
  assert.ok(Math.abs(loud(on).lufs + 14) <= 0.5, `true is the default: ${loud(on).lufs}`);
  const log = [];
  writeFileSync(join(root, M('media/b/w/p/loud-cli.edit.json')), JSON.stringify(quiet));
  main(['--list', M('media/b/w/p/loud-cli.edit.json'), '--out', M('media/b/w/p/loud-cli.mp4')], { root, log: (l) => log.push(l) });
  assert.match(log.at(-1), /^wrote .* -1[34]\.\d LUFS, -\d+\.\d dBTP\) and loud-cli\.mp4\.json$/);
});

test('the line printed says when the sound missed its target, was left off or silent, or was turned up a lot', () => {
  const line = (loudness) => wrote('m/r.mp4', { seconds: 4, parts: [{}], ai_generated: false, loudness });
  const was = { lufs: -30, true_peak: -20 };
  assert.equal(line({ lufs: -14.1, true_peak: -1.5, before: was }), 'wrote m/r.mp4 (4 s, 1 parts, ai_generated false, -14.1 LUFS, -1.5 dBTP) and r.mp4.json');
  for (const missed of [{ lufs: -14.7, true_peak: -1.5 }, { lufs: -14, true_peak: -0.9 }]) {
    assert.match(line({ ...missed, before: was }), /dBTP, off the target of -14 LUFS and -1 dBTP\) and/, JSON.stringify(missed));
  }
  assert.match(line({ lufs: -16.3, true_peak: -3, off: true }), /-16\.3 LUFS, -3\.0 dBTP, loudness off\) and/);
  assert.match(line({ lufs: null, true_peak: null, silent: true }), /-inf LUFS, -inf dBTP, silent, left as it is\) and/);
  assert.match(line({ lufs: -14, true_peak: -2, before: { lufs: -45, true_peak: -30 } }), /dBTP, turned up 31\.0 dB: listen for noise\) and/);
  assert.match(line({ lufs: -14, true_peak: -2, before: { lufs: -34, true_peak: -20 } }), /-2\.0 dBTP\) and/, 'a 20 dB boost is no news');
});

test('hostile edit lists are refused', () => {
  symlinkSync('/etc/hosts', join(root, M('inbox/link.mp4')));
  writeFileSync(join(root, 'outside-root.mp4'), 'x');
  const bad = [
    [{ clips: [{ file: 'https://example.test/a.mp4', in: 0, out: 1 }] }, /URL/],
    [{ clips: [{ file: 'file:/etc/hosts', in: 0, out: 1 }] }, /URL|protocol/],
    [{ clips: [{ file: M('inbox/../../../outside-root.mp4'), in: 0, out: 1 }] }, /must be a file in/],
    [{ clips: [{ file: M('inbox/link.mp4'), in: 0, out: 1 }] }, /must be a file in/],
    [{ clips: [{ file: own, in: 0, out: 1 }], music: { file: outside } }, /music bed/],
    [{ clips: [{ file: own, in: 0, out: 1 }], subtitles: '/etc/hosts' }, /refused/],
    [{ clips: [{ file: own, in: 0, out: 9 }] }, /past the clip's end/],
    [{ clips: [{ file: own, in: null, out: '' }] }, /must be a number/],
  ];
  bad.forEach(([list, why], i) => assert.throws(() => compile(list, join(root, M(`media/b/w/p/bad-${i}.mp4`)), { root }), why));
  // An outside file whose manifest doesn't know it.
  writeFileSync(join(root, M('sources/b/w/clip/other.mp4')), readFileSync(join(root, own)));
  assert.throws(() => compile({ clips: [{ file: M('sources/b/w/clip/other.mp4'), in: 0, out: 1 }] },
    join(root, M('media/b/w/p/x.mp4')), { root }), /no MANIFEST.json entry/);
  // Output only as a new .mp4 inside media/.
  for (const out of [join(root, 'reel.mp4'), join(root, M('inbox/reel.mp4')), join(root, M('media/b/w/p/reel.mp4')), 'file:/tmp/r.mp4']) {
    assert.throws(() => compile({ clips: [{ file: own, in: 0, out: 1 }] }, out, { root }), /refused/);
  }
});

test('silences pair up in order, and a pre-roll start counts from 0', () => {
  const report = 'silence_start: -0.012\nsilence_end: 0.8 | silence_duration: 0.8\nsilence_start: 2.1\nsilence_end: 3.0\nsilence_start: 3.9';
  assert.deepEqual(silences(report, 4.5), [[0, 0.8], [2.1, 3], [3.9, 4.5]]);
});

test('a file posing as video but holding a playlist is never followed', () => {
  writeFileSync(join(root, M('inbox/fake.mp4')), `#EXTM3U\n#EXTINF:1,\n${join(root, 'outside-root.mp4')}\n#EXT-X-ENDLIST\n`);
  writeFileSync(join(root, M('inbox/list.m3u8')), '#EXTM3U\n');
  assert.throws(() => compile({ clips: [{ file: M('inbox/list.m3u8'), in: 0, out: 1 }] }, join(root, M('media/b/w/p/pl1.mp4')), { root }), /only/);
  assert.throws(() => compile({ clips: [{ file: M('inbox/fake.mp4'), in: 0, out: 1 }] }, join(root, M('media/b/w/p/pl2.mp4')), { root }), /refused|ffmpeg failed/);
});

test('outputs are never written through a link', () => {
  const victim = join(root, 'victim.txt');
  writeFileSync(victim, 'untouched');
  symlinkSync(victim, join(root, M('media/b/w/p/l1.mp4.json')));
  symlinkSync(join(root, 'nowhere.mp4'), join(root, M('media/b/w/p/l2.mp4')));  // dangling
  for (const out of ['l1.mp4', 'l2.mp4']) {
    assert.throws(() => compile({ clips: [{ file: own, in: 0, out: 1 }] }, join(root, M(`media/b/w/p/${out}`)), { root }), /no file or link/);
  }
  assert.equal(readFileSync(victim, 'utf8'), 'untouched');
});

test('the overlay shows only in its interval, the voice starts on time, and music ducks under speech', () => {
  const rel = M('media/b/w/p/timing.mp4');
  compile({ clips: [{ file: outside, in: 0, out: 3 }, { file: broll, in: 0, out: 2 }],
    overlays: [{ file: overlay, start: 1, end: 2, y: 250 }], voice: { file: voice, start: 1.5 }, music: { file: song, volume: 0.5 } },
  join(root, rel), { root });
  assert.ok(teal(pixel(rel, 1.5, 540, 450)), `inside: ${pixel(rel, 1.5, 540, 450)}`);
  assert.ok(!teal(pixel(rel, 0.5, 540, 450)) && !teal(pixel(rel, 2.5, 540, 450)), 'outside the interval');
  assert.ok(level(rel, 1.7, 3.3, 660) - level(rel, 0.2, 1.3, 660) > 20, 'the voice starts at 1.5 s');
  // The song is 2 s and loops; speech (the voice) runs 1.5-3.5 s, so the bed is ducked there and back up after.
  assert.ok(level(rel, 3.8, 4.8, 220) - level(rel, 1.8, 3.3, 220) > 6, `ducking: ${level(rel, 1.8, 3.3, 220)} vs ${level(rel, 3.8, 4.8, 220)}`);
});

// --batch and --vars: the session kits' drop-in of his voice and footage.
const vars = (name, content) => {
  writeFileSync(join(root, M(`media/b/w/p/${name}.json`)), typeof content === 'string' ? content : JSON.stringify(content));
  return M(`media/b/w/p/${name}.json`);
};
const editLists = (folder, lists) => {
  mkdirSync(join(root, M(folder)), { recursive: true });
  for (const [name, list] of Object.entries(lists)) {
    writeFileSync(join(root, M(`${folder}/${name}.edit.json`)), typeof list === 'string' ? list : JSON.stringify(list));
  }
  return M(folder);
};

test('vars retime a list along its map, swap its clips for as long as their stretch, and replace its voice', () => {
  const list = {
    clips: [{ file: bands, in: 0, out: 2 }, { file: outside, in: 0.5, out: 2.5, volume: 0 }],
    overlays: [{ file: overlay, start: 0, end: 1 }, { file: overlay, start: 1, end: 4, y: 9 }],
    zooms: [{ start: 0, end: 2, scale: 1.1 }], sfx: [{ file: beep, start: 3 }], voice: { file: voice, start: 0.5 }, grade: { contrast: 1.1 },
  };
  const retime = [{ match: 'nope', map: [[0, 9]] }, { match: ['x-', 'y-'], map: [[0, 0], [1, 'a'], [4, 'b']] }];
  const moved = applyVars(list, 'reel-y-1', readVars(vars('v-retime', { times: { a: 1.5, b: 5 }, retime }), root));
  // 0-1 s stretches to 0-1.5 s, 1-4 s to 1.5-5 s.
  assert.deepEqual(moved.clips, [{ file: bands, in: 0, out: 2.667 }, { file: outside, in: 0.5, out: 2.833, volume: 0 }]);
  assert.deepEqual(moved.overlays, [{ file: overlay, start: 0, end: 1.5 }, { file: overlay, start: 1.5, end: 5, y: 9 }]);
  assert.deepEqual([moved.zooms, moved.sfx[0].start, moved.voice, moved.grade], [[{ start: 0, end: 2.667, scale: 1.1 }], 3.833, { file: voice, start: 0.75 }, { contrast: 1.1 }]);
  assert.deepEqual(list.clips[0], { file: bands, in: 0, out: 2 }, 'the list itself is untouched');
  // Past the last point and before the first, times move with it, one second for one.
  const shifted = applyVars(list, 'n', readVars(vars('v-shift', { retime: [{ match: 'n', map: [[1, 2]] }] }), root));
  assert.deepEqual([shifted.overlays[0].start, shifted.overlays[1].end, shifted.clips[1].out], [1, 5, 2.5]);
  // A swap starts at its own in and lasts as long as the clip it replaces; the vars' voice replaces the list's.
  const swap = { [bands]: { file: own, in: 1 }, 'workspaces/marketing/media/none.png': { file: own } };
  const swapped = applyVars(list, 'reel-y-1', readVars(vars('v-swap', { voice: { file: voice, start: 0 }, swap, times: { a: 1.5, b: 5 }, retime }), root));
  assert.deepEqual([swapped.clips[0], swapped.clips[1].out, swapped.voice], [{ file: own, in: 1, out: 3.667 }, 2.833, { file: voice, start: 0 }]);
  assert.deepEqual(applyVars(list, 'n', readVars(vars('v-swap-only', { swap }), root)).clips, [{ file: own, in: 1, out: 3 }, list.clips[1]]);
  assert.deepEqual(applyVars(list, 'n', {}), list);
});

test('vars that are unclear or hostile are refused, and so is a list they can\'t retime', () => {
  const bad = [
    [{ retime: [{ match: 'a', map: [[0, 0], [1, 2], [1, 3]] }] }, /rise in both/],
    [{ retime: [{ match: 'a', map: [[0, 0], [1, 0]] }] }, /rise in both/],
    [{ retime: [{ match: 'a', map: [[0, 'c9']] }] }, /no time named c9/],
    [{ retime: [{ match: 'a', map: [[0, 'toString']] }] }, /no time named toString/],
    [{ times: { x: '1; rm' }, retime: [{ match: 'a', map: [[0, 'x']] }] }, /must be a number/],
    [{ times: { unused: 'soon' } }, /times\.unused must be a number/],
    [{ retime: [{ match: 'a', map: [[1, 0.5]] }] }, /start before 0/],
    [{ retime: [] }, /list of rules/],
    [{ retime: [{ match: 'a', map: [[0, 0, 1]] }] }, /\[old, new\]/],
    [{ retime: [{ match: 'a', map: [] }] }, /at least one/],
    [{ retime: [{ map: [[0, 0]] }] }, /match/],
    [{ retime: [{ match: ['a', ''], map: [[0, 0]] }] }, /match/],
    [{ retime: { match: 'a' } }, /list of rules/],
    [{ swap: { [bands]: own } }, /swap/],
    [{ voice: voice }, /voice must be an object/],
    [{ times: [1] }, /times/],
    [{ colour: 'warm' }, /has only voice, swap, times, retime, not colour/],
    [[1, 2], /one JSON object/],
  ];
  bad.forEach(([content, why], i) => assert.throws(() => readVars(vars(`v-bad-${i}`, content), root), why));
  assert.throws(() => readVars(vars('v-broken', '{"retime": '), root), /JSON/);
  writeFileSync(join(root, 'v.json'), '{}');
  assert.throws(() => readVars('v.json', root), /must be a file in/);
  const rules = readVars(vars('v-rule', { retime: [{ match: '-end-', map: [[0, 0]] }] }), root);
  const clips = [{ file: bands, in: 0, out: 1 }, { file: outside, in: 0, out: 1 }];
  assert.throws(() => applyVars({ clips }, 'reel-key-1', rules), /no retime rule matches/);
  for (const list of [{ clips, cuts: [{ clip: 0, from: 0.2, to: 0.4 }] }, { clips, subtitles: M('inbox/take.srt') },
    { clips: [clips[0], { ...clips[1], crossfade: 0.5 }] }]) assert.throws(() => applyVars(list, 'reel-end-1', rules), /can't be retimed/);
  assert.throws(() => applyVars({ clips: [] }, 'n', rules), /needs clips/);
});

test('a batch builds every edit list in the folder, each with its own provenance record', () => {
  const folder = editLists('media/b/w/batch-ok', {
    'reel-a': { clips: [{ file: bands, in: 0, out: 1 }], overlays: [{ file: overlay, start: 0, end: 1 }] },
    'reel-b': { clips: [{ file: outside, in: 0, out: 1 }] },
  });
  writeFileSync(join(root, folder, 'notes.txt'), 'not an edit list');
  const usedBefore = (JSON.parse(readFileSync(join(root, M('sources/b/w/clip/MANIFEST.json')), 'utf8')).files[0].used || []).length;
  const log = [];
  const results = batch(folder, M('media/b/w/batch-ok-out'), vars('v-batch', {
    voice: { file: voice, start: 0 }, swap: { [bands]: { file: own, in: 0.5 }, [broll]: { file: own } },
    times: { c: 2 }, retime: [{ match: ['reel-a', 'reel-b'], map: [[0, 0], [1, 'c']] }],
  }), { root, log: (line) => log.push(line) });
  assert.deepEqual(results.map((r) => [r.name, r.error]), [['reel-a', undefined], ['reel-b', undefined]]);
  for (const { name, out, record } of results) {
    assert.equal(out, join(root, M(`media/b/w/batch-ok-out/${name}.mp4`)));
    assert.deepEqual(JSON.parse(readFileSync(`${out}.json`, 'utf8')), record);
    assert.equal(record.seconds, 2);
    assert.ok(Math.abs(seconds(M(`media/b/w/batch-ok-out/${name}.mp4`)) - 2) < 0.15);
    assert.equal(record.ai_generated, false);
  }
  const [a, b] = results.map((r) => Object.fromEntries(r.record.inputs.map((i) => [i.file, i])));
  assert.deepEqual([a[own].provenance, a[voice].provenance, a[overlay].provenance, a[bands]], ['own-footage', 'own-render', 'own-render', undefined]);
  assert.deepEqual(results[0].record.parts, [{ file: own, from: 0.5, to: 2.5, at: 0 }]);
  assert.deepEqual([b[outside].provenance, b[outside].sha256], ['outside', sha(outside)]);
  const used = JSON.parse(readFileSync(join(root, M('sources/b/w/clip/MANIFEST.json')), 'utf8')).files[0].used;
  assert.deepEqual(used.slice(usedBefore).map((u) => [u.from, u.to]), [[0, 2]]);
  assert.equal(log.filter((l) => l.startsWith('wrote ')).length, 2);
  assert.ok(log.includes(`note: swap ${broll} matches no clip in ${folder}`), log.join('\n'));
  // Run again into the same folder: every reel is refused, nothing is overwritten.
  assert.ok(batch(folder, M('media/b/w/batch-ok-out'), null, { root }).every((r) => /must be a new \.mp4/.test(r.error)));
});

test('in a batch, a reel that fails is named and the rest are built', () => {
  const folder = editLists('media/b/w/batch-some', {
    good: { clips: [{ file: outside, in: 0, out: 1 }] },
    long: { clips: [{ file: outside, in: 0, out: 9 }] },
    hostile: { clips: [{ file: own, in: 0, out: 1 }], subtitles: '/etc/hosts' },
  });
  const results = batch(folder, M('media/b/w/batch-some-out'), null, { root });
  assert.deepEqual(results.map((r) => r.name), ['good', 'hostile', 'long']);
  assert.ok(results[0].record && !results[0].error);
  assert.match(results[1].error, /refused/);
  assert.match(results[2].error, /past the clip's end/);
  // Outputs only into media/, by compile's own check.
  assert.ok(batch(folder, M('inbox/batch-out'), null, { root }).every((r) => /must be in workspaces\/marketing\/media/.test(r.error)));
  // The command line names them and exits 1.
  const [log, error] = [[], []];
  const code = main(['--batch', folder, '--dir', M('media/b/w/batch-some-cli')], { root, log: (l) => log.push(l), error: (l) => error.push(l) });
  assert.deepEqual([code, error.at(-1), log.filter((l) => l.startsWith('wrote ')).length], [1, '2 reels not built: hostile, long', 1]);
  assert.ok(existsSync(join(root, M('media/b/w/batch-some-cli/good.mp4.json'))));
});

test('a batch with a list it can\'t read or change builds nothing', () => {
  const folder = editLists('media/b/w/batch-none', {
    'reel-end-1': { clips: [{ file: outside, in: 0, out: 1 }] },
    'reel-key-1': { clips: [{ file: outside, in: 0, out: 1 }] },
    broken: '{"clips": ',
  });
  symlinkSync(join(root, 'v.json'), join(root, folder, 'outside.edit.json'));
  const retime = vars('v-end-only', { retime: [{ match: '-end-', map: [[0, 0]] }] });
  assert.throws(() => batch(folder, M('media/b/w/batch-none-out'), retime, { root }),
    (e) => /^refused: nothing built; 3 of 4 lists:/.test(e.message) && /broken: .*JSON/.test(e.message)
      && /outside: .*must be a file in/.test(e.message) && /reel-key-1: .*no retime rule/.test(e.message));
  assert.ok(!existsSync(join(root, M('media/b/w/batch-none-out'))));
  mkdirSync(join(root, M('media/b/w/batch-empty')));
  assert.throws(() => batch(M('media/b/w/batch-empty'), M('media/b/w/x'), null, { root }), /has no \.edit\.json files/);
  assert.throws(() => batch(M('media/b/w/batch-empty'), '', null, { root }), /need a folder each/);
  // The folder itself must be one the lists may come from: its names aren't listed otherwise.
  mkdirSync(join(root, 'elsewhere'));
  writeFileSync(join(root, 'elsewhere/secret-name.edit.json'), '{}');
  symlinkSync(join(root, 'elsewhere'), join(root, M('media/b/w/batch-link')));
  for (const away of ['elsewhere', join(root, 'elsewhere'), M('media/b/w/batch-link'), M('media/b/w/none'), M('media/b/w/batch-none/broken.edit.json')]) {
    assert.throws(() => batch(away, M('media/b/w/x'), null, { root }), (e) => /must be a folder in workspaces\/marketing\/inbox/.test(e.message)
      && !/secret-name/.test(e.message), away);
  }
});

test('the command line takes one list or one batch, not a mix', () => {
  const script = join(import.meta.dirname, '../video/compile.mjs');
  for (const args of [['--batch', 'x'], ['--dir', 'x'], ['--batch', 'x', '--dir', 'y', '--out', 'z.mp4'], ['--list', 'x', '--out', 'y', '--vars', 'v.json'],
    ['--batch', 'x', '--dir', 'y', '--list', 'z']]) {
    const run = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
    assert.equal(run.status, 2, `${args.join(' ')}: ${run.stderr}`);
    assert.match(run.stderr, /--batch <folder of \.edit\.json> --dir/);
  }
});
