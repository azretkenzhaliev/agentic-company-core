#!/usr/bin/env node
// Compile a reel from an edit list: clips cut and joined, pauses removed, our overlays, subtitles, his voice and
// a music bed ducked under speech, into one 1080x1920 30 fps MP4.
//
//   node video/compile.mjs --list <edit-list.json> --out workspaces/marketing/media/<brand>/<week>/<piece>/reel.mp4
//   node video/compile.mjs --list <edit-list.json> --propose-cuts      # prints pause cuts; accepted ones go in "cuts"
//   node video/compile.mjs --batch <folder> --dir workspaces/marketing/media/<...> [--vars <vars.json>]
//
// --batch builds every <name>.edit.json in the folder (in inbox/, media/ or sources/), in name order, to <dir>/<name>.mp4
// and its .mp4.json, each with the checks below; a reel that fails is named and the rest go on (exit 1 if any failed).
// --vars, a .json file there too, changes every list first, and a list it can't change stops the batch before anything is built:
// {
//   "voice":  { "file": "...", "start": 0, "volume": 1 },              replaces each list's voice
//   "swap":   { "<a clip's file, as the lists write it>": { "file": "...", "in": 12, "volume": 0 } },
//                                                                      that clip becomes this one (its own volume and ai,
//                                                                      nothing kept but the length), from its in
//   "times":  { "c1": 1.02, "c2": 11.8 },                             named seconds, for the maps
//   "retime": [{ "match": ["-end-", "note-reel"], "map": [[0, 0], [0.95, "c1"], [10.45, "c2"]] }]
// }
// The first retime rule with a match in the list's name moves its times along straight lines through the [old, new]
// points (slope 1 before the first and after the last; both columns rising): every reel time below (overlays, zooms,
// sfx, the voice's start) and where each clip ends, so a clip is as much longer as its stretch of the reel. A map that
// moves 0 later lengthens the first clip by as much; one that moves it earlier is refused. With retime, every list in
// the folder needs a rule, so give each family of lists its own folder; a list no rule matches, or one with cuts,
// crossfades or subtitles, stops the batch.
//
// The edit list. Paths are relative to the repo root; each must be a file in workspaces/marketing/inbox/,
// media/ or sources/ (links resolved; no URLs):
// {
//   "clips":     [{ "file": "...", "in": 2.0, "out": 9.5, "srt": "optional, in the clip's own time", "volume": 1,
//                   "crossfade": 0.4,                                 seconds of dissolve from the clip before, at least 0.1; the reel gets that much shorter
//                   "crop": { "corner": "bottom-left", "size": 0.8 } }],  the clip's frame cut to a 9:16 window in that corner (top-left,
//                                                                      top-right, bottom-left, bottom-right), size 0.5 to 1 of the largest one
//   "cuts":      [{ "clip": 0, "from": 4.1, "to": 4.8 }],             accepted pause cuts, in the clip's own time
//   "overlays":  [{ "file": "....png | .mov | .webm", "start": 0, "end": 2.5, "x": 0, "y": 0 }],
//   "subtitles": "optional SRT in the reel's own time, e.g. for the voice track",
//   "voice":     { "file": "...", "start": 0, "volume": 1 },
//   "music":     { "file": "...", "volume": 0.2 },                      ducked under speech
//   "sfx":       [{ "file": "...", "start": 3.2, "volume": 1 }],        sound effects; they don't duck the music
//   "zooms":     [{ "start": 3, "end": 4, "scale": 1.08, "ease": "sine" }],  a centred push, scale above 1, at most 2. "sine" (the default):
//                                                                      in to scale at the middle and back. "linear": in at an even speed,
//                                                                      at scale by the end, then back at once, so end it on a cut
//   "grade":     { "contrast": 1.05, "saturation": 1.1, "brightness": 0.02, "gamma": 1, "warmth": 0.3 }   any of these. warmth is
//                                                                      a colour temperature: 1 warmer (4000 K), -1 cooler (9000 K), 0 none
//   "loudness":  false                                                 the sound is mastered to -14 LUFS, at most -1 dBTP, unless this says false
// }
// A clip may be a still image (.png, .jpg), shown for out - in seconds. Any input may say "ai": true. Every start and
// end but a clip's own is in the reel's final time, after cuts and crossfades. Crops, zooms and the grade touch the
// footage, never our overlays or subtitles.
// Writes <out> and <out>.json: every input with its provenance (own-footage from inbox/, own-render from media/,
// ai-generated when its <file>.json sidecar or the list says so, outside from sources/ with its MANIFEST.json
// entry's SHA-256), the parts used, ai_generated, and the sound's loudness as measured in <out> (and before mastering;
// a reel quieter than -50 LUFS counts as silent and is left as it is). An outside file needs a manifest entry with its SHA-256, and
// an outside clip's entry gets the parts used appended. A music bed or sound effect baked in must be ours, or outside
// with "music_ok": true in its entry (a licence that allows it, on the Board's word; a licence fetch.py recorded isn't
// that); the default for music is Instagram's own library, attached at publishing.
// ffmpeg opens files only (-protocol_whitelist file before every input); the output goes only into media/.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants, copyFileSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import ffmpeg from 'ffmpeg-static';
import { DEMUXER, demuxer } from './formats.mjs';
import { STYLE, escapeFilter, golosFontsDir } from './subtitles.mjs';

const REPO = fileURLToPath(new URL('../../..', import.meta.url));
const BASES = { inbox: 'workspaces/marketing/inbox', media: 'workspaces/marketing/media', sources: 'workspaces/marketing/sources' };
const W = 1080, H = 1920, FPS = 30, MAX_SECONDS = 900, MIN_PART = 0.05;
const IMAGE = /\.(png|jpe?g)$/i;
const TEXT = new Set(['.srt', '.json']);  // read by this script, never by ffmpeg
// One colour standard for every part (phone HDR clips are HLG): tagged BT.709, not tone-mapped.
const SDR = 'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv';
const MAX_ZOOM = 2, MIN_CROSSFADE = 0.1;
const GRADE = { contrast: [0.5, 2], saturation: [0, 3], brightness: [-0.3, 0.3], gamma: [0.5, 2], warmth: [-1, 1] };
const EASES = ['sine', 'linear'];
const CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
// The sound's target (craft-standard.md, "Loudness"): integrated LUFS and the highest true peak, in dBTP.
const LUFS = -14, TRUE_PEAK = -1, SILENT_LUFS = -50, LOUD_BOOST = 20, TAKES = 5;

const within = (path, base) => {
  const rel = relative(base, path);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
};
const num = (v, name) => {
  const n = typeof v === 'number' || (typeof v === 'string' && v.trim() !== '') ? Number(v) : NaN;
  if (!Number.isFinite(n)) throw new Error(`refused: ${name} must be a number`);
  return n;
};
const sha256 = (file) => createHash('sha256').update(readFileSync(file)).digest('hex');

// A real file in inbox/, media/ or sources/, and which of them.
export function inputPath(path, root = REPO) {
  if (typeof path !== 'string' || !path || path.includes('://') || /^[a-z][a-z0-9+.-]*:/i.test(path)) {
    throw new Error(`refused: ${path} must be a local file path, no URLs or protocols`);
  }
  const ext = extname(path).toLowerCase();
  if (!(ext in DEMUXER) && !TEXT.has(ext)) {
    throw new Error(`refused: ${path}: only ${[...Object.keys(DEMUXER), ...TEXT].join(' ')} files`);
  }
  const full = isAbsolute(path) ? path : join(root, path);
  const real = existsSync(full) ? realpathSync(full) : null;
  if (!real || !statSync(real).isFile()) throw new Error(`refused: ${path} isn't a file`);
  for (const [kind, base] of Object.entries(BASES)) {
    const b = join(root, base);
    if (existsSync(b) && within(real, realpathSync(b))) return { real, kind };
  }
  throw new Error(`refused: ${path} must be a file in workspaces/marketing/inbox/, media/ or sources/`);
}

function manifestEntry(real) {
  const manifest = join(dirname(real), 'MANIFEST.json');
  const sha = sha256(real);
  let files = [];
  try {
    files = JSON.parse(readFileSync(manifest, 'utf8')).files || [];
  } catch {
    throw new Error(`refused: ${real} is outside footage with no readable MANIFEST.json beside it`);
  }
  const entry = files.find((e) => e && e.sha256 === sha);
  if (!entry) throw new Error(`refused: ${real} has no MANIFEST.json entry with its SHA-256 (${sha.slice(0, 12)}…)`);
  return { manifest, sha, entry };
}

// Provenance of one input: outside (with its manifest), ai-generated, own-footage or own-render.
export function provenance(path, { ai = false, root = REPO } = {}) {
  const { real, kind } = inputPath(path, root);
  const base = realpathSync(root);
  const rel = relative(base, real) || real;
  if (kind === 'sources') {
    const { manifest, sha, entry } = manifestEntry(real);
    return { file: rel, real, provenance: 'outside', sha256: sha, manifest: relative(base, manifest), source_url: entry.source_url,
      owner: entry.owner, licence: entry.licence || null, music_ok: entry.music_ok === true, ai_generated: !!ai };
  }
  let sidecarAi = false;
  try { sidecarAi = JSON.parse(readFileSync(`${real}.json`, 'utf8')).ai_generated === true; } catch { /* no sidecar */ }
  if (ai || sidecarAi) return { file: rel, real, provenance: 'ai-generated', ai_generated: true };
  return { file: rel, real, provenance: kind === 'inbox' ? 'own-footage' : 'own-render', ai_generated: false };
}

function probe(file) {
  const run = spawnSync(ffmpeg, ['-hide_banner', '-protocol_whitelist', 'file', ...demuxer(file), '-i', file], { encoding: 'utf8' });
  const d = run.stderr.match(/Duration: (\d+):(\d+):([\d.]+)/);
  return {
    duration: d ? Number(d[1]) * 3600 + Number(d[2]) * 60 + Number(d[3]) : null,
    audio: /Stream #\S+.*: Audio:/.test(run.stderr),
  };
}

// The clips' kept parts, in reel order, after the accepted cuts; a crossfade starts a part that much earlier.
export function segments(clips, cuts = []) {
  const parts = [];
  let at = 0;
  clips.forEach((clip, i) => {
    const [a, b] = [num(clip.in ?? 0, `clips[${i}].in`), num(clip.out, `clips[${i}].out`)];
    if (!(a >= 0 && b > a)) throw new Error(`refused: clips[${i}] needs 0 <= in < out`);
    const crossfade = num(clip.crossfade ?? 0, `clips[${i}].crossfade`);
    if (crossfade !== 0 && (crossfade < MIN_CROSSFADE || !parts.length)) throw new Error(`refused: clips[${i}].crossfade needs at least ${MIN_CROSSFADE} s and a clip before it`);
    let kept = [[a, b]];
    for (const c of cuts.filter((c) => c.clip === i)) {
      const [f, t] = [num(c.from, 'cuts.from'), num(c.to, 'cuts.to')];
      if (!(t > f)) throw new Error('refused: a cut needs from < to');
      kept = kept.flatMap(([s, e]) => [[s, Math.min(e, f)], [Math.max(s, t), e]]).filter(([s, e]) => e - s >= MIN_PART);
    }
    kept.forEach(([s, e], k) => {
      const fade = k === 0 ? crossfade : 0;
      at -= fade;
      parts.push({ clip: i, from: s, to: e, at, fade });
      at += e - s;
    });
  });
  if (!parts.length) throw new Error('refused: nothing left to show');
  parts.forEach((p, k) => {
    if (p.fade + (parts[k + 1]?.fade ?? 0) >= p.to - p.from) throw new Error(`refused: a part of clips[${p.clip}] is too short for its crossfades`);
  });
  if (at > MAX_SECONDS) throw new Error(`refused: the reel would be ${at.toFixed(1)} s; at most ${MAX_SECONDS}`);
  return parts;
}

// SRT in, cues out ({ start, end, text } in seconds), and back.
const SRT_TIME = /(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)/;
export function parseSrt(text) {
  return text.replace(/\r/g, '').split(/\n\s*\n/).map((block) => {
    const lines = block.trim().split('\n');
    const i = lines.findIndex((l) => SRT_TIME.test(l));
    if (i < 0) return null;
    const m = lines[i].match(SRT_TIME).slice(1).map(Number);
    return { start: m[0] * 3600 + m[1] * 60 + m[2] + m[3] / 1000, end: m[4] * 3600 + m[5] * 60 + m[6] + m[7] / 1000,
      text: lines.slice(i + 1).join('\n') };
  }).filter((c) => c && c.text && c.end > c.start);
}
const stamp = (s) => {
  const ms = Math.max(0, Math.round(s * 1000));
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
};
export const formatSrt = (cues) => cues.map((c, i) => `${i + 1}\n${stamp(c.start)} --> ${stamp(c.end)}\n${c.text}\n`).join('\n');

// A clip's cues (in its own time) moved onto the reel's time through the kept parts; cut words drop out.
export function remapCues(cues, parts) {
  const out = [];
  for (const c of cues) {
    for (const p of parts) {
      const [s, e] = [Math.max(c.start, p.from), Math.min(c.end, p.to)];
      if (e - s >= MIN_PART) out.push({ start: p.at + s - p.from, end: p.at + e - p.from, text: c.text });
    }
  }
  return out;
}

// silencedetect's report as [start, end] pairs, in order; a start before 0 (pre-roll) counts from 0.
export function silences(stderr, length) {
  const pairs = [];
  let open = null;
  for (const m of stderr.matchAll(/silence_(start|end): (-?[\d.]+)/g)) {
    const at = Math.max(0, Number(m[2]));
    if (m[1] === 'start') open = at;
    else if (open !== null) { pairs.push([open, at]); open = null; }
  }
  if (open !== null) pairs.push([open, length]);
  return pairs;
}

// Pauses in each clip, as proposed cuts in its own time, padded so words aren't clipped.
export function proposeCuts(list, { root = REPO, noiseDb = -35, minSilence = 0.6, pad = 0.15 } = {}) {
  const cuts = [];
  (list.clips || []).forEach((clip, i) => {
    const { real } = inputPath(clip.file, root);
    if (IMAGE.test(real) || !probe(real).audio) return;
    const [a, b] = [num(clip.in ?? 0, 'in'), num(clip.out, 'out')];
    const run = spawnSync(ffmpeg, ['-hide_banner', '-nostats', '-protocol_whitelist', 'file', '-ss', String(a), '-t', String(b - a),
      ...demuxer(real), '-i', real, '-af', `silencedetect=noise=${noiseDb}dB:d=${minSilence}`, '-f', 'null', '-'], { encoding: 'utf8' });
    if (run.status !== 0) throw new Error(`ffmpeg failed: ${run.stderr}`);
    for (const [s, e] of silences(run.stderr, b - a)) {
      if (e - s - 2 * pad >= 0.3) cuts.push({ clip: i, from: +(a + s + pad).toFixed(3), to: +(a + e - pad).toFixed(3) });
    }
  });
  return { cuts };
}

// The footage's look, as ffmpeg filters: the grade (warmth first), then the zooms. Every value is a checked number.
function lookFilters(grade, zooms) {
  const filters = [];
  if (grade) {
    if (typeof grade !== 'object') throw new Error('refused: grade must be an object');
    const settings = Object.entries(grade).map(([key, value]) => {
      if (!Object.hasOwn(GRADE, key)) throw new Error(`refused: grade has only ${Object.keys(GRADE).join(', ')}, not ${key}`);
      const n = num(value, `grade.${key}`);
      if (!(n >= GRADE[key][0] && n <= GRADE[key][1])) throw new Error(`refused: grade.${key} must be ${GRADE[key].join(' to ')}`);
      return [key, n];
    });
    // Warmth as a colour temperature, lightness kept: 6500 K is neutral, lower is warmer. 0 adds nothing.
    const warmth = settings.find(([key]) => key === 'warmth')?.[1];
    if (warmth) filters.push(`colortemperature=temperature=${Math.round(6500 - 2500 * warmth)}:pl=1,format=yuv420p`);
    const eq = settings.filter(([key]) => key !== 'warmth');
    if (eq.length) filters.push(`eq=${eq.map(([key, n]) => `${key}=${n}`).join(':')}`);
  }
  const pushes = zooms.map((z, i) => {
    const [s, e, scale] = [num(z.start, `zooms[${i}].start`), num(z.end, `zooms[${i}].end`), num(z.scale, `zooms[${i}].scale`)];
    if (!(s >= 0 && e > s)) throw new Error(`refused: zooms[${i}] needs 0 <= start < end`);
    if (!(scale > 1 && scale <= MAX_ZOOM)) throw new Error(`refused: zooms[${i}].scale must be above 1, at most ${MAX_ZOOM}`);
    const ease = z.ease === undefined ? 'sine' : z.ease;
    if (!EASES.includes(ease)) throw new Error(`refused: zooms[${i}].ease must be ${EASES.join(' or ')}`);
    const u = `clip((it-${s.toFixed(3)})/${(e - s).toFixed(3)},0,1)`;
    return ease === 'linear' ? `${(scale - 1).toFixed(4)}*${u}*lte(it,${e.toFixed(3)})` : `${(scale - 1).toFixed(4)}*sin(PI*${u})`;
  });
  // 4:4:4 while zooming: zoompan rounds its crop to the chroma grid, which shakes the frame twice as much in 4:2:0.
  if (pushes.length) filters.push(`format=yuv444p,zoompan=z='1+${pushes.join('+')}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=${W}x${H}:fps=${FPS},format=yuv420p`);
  return filters.join(',');
}

// A clip's corner crop, as an ffmpeg filter and a comma, or nothing: a 9:16 window of size times the largest one, in that corner.
function cropFilter(crop, i) {
  if (crop === undefined) return '';
  if (!isObject(crop)) throw new Error(`refused: clips[${i}].crop must be an object`);
  const unknown = Object.keys(crop).filter((k) => k !== 'corner' && k !== 'size');
  if (unknown.length) throw new Error(`refused: clips[${i}].crop has only corner and size, not ${unknown.join(', ')}`);
  if (!CORNERS.includes(crop.corner)) throw new Error(`refused: clips[${i}].crop.corner must be ${CORNERS.join(', ')}`);
  const size = num(crop.size, `clips[${i}].crop.size`);
  if (!(size >= 0.5 && size <= 1)) throw new Error(`refused: clips[${i}].crop.size must be 0.5 to 1`);
  const [y, x] = crop.corner.split('-');
  const w = `${size}*min(iw,ih*${W}/${H})`;
  return `crop=w='trunc(${w}/2)*2':h='trunc(${w}*${H}/${W}/2)*2':x=${x === 'left' ? 0 : 'iw-ow'}:y=${y === 'top' ? 0 : 'ih-oh'},`;
}

function ffmpegRun(args) {
  const run = spawnSync(ffmpeg, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (run.status !== 0) throw new Error(`ffmpeg failed: ${run.stderr}`);
  return run.stderr;
}

// A file's sound by EBU R128: integrated loudness in LUFS and true peak in dBTP; null where there's no signal.
function loudness(file) {
  const stderr = ffmpegRun(['-hide_banner', '-nostats', '-protocol_whitelist', 'file', ...demuxer(file), '-i', file, '-map', '0:a:0',
    '-af', 'ebur128=peak=true:framelog=verbose', '-f', 'null', '-']);
  const summary = stderr.slice(stderr.lastIndexOf('Summary:'));
  const value = (re) => {
    const m = summary.match(re);
    if (!m) throw new Error(`ffmpeg measured no loudness in ${file}`);
    return m[1] === '-inf' ? null : Number(m[1]);
  };
  return { lufs: value(/I:\s+(-?[\d.]+|-inf) LUFS/), true_peak: value(/Peak:\s+(-?[\d.]+|-inf) dBFS/) };
}

// The reel's sound as AAC, mastered to LUFS with true peaks at most TRUE_PEAK unless on is false: measured, turned up or
// down, through a true-peak limiter (4x oversampled) wherever the gain would push a peak above a ceiling 1 dB under
// TRUE_PEAK, encoded, and measured again, since the encoder moves both; the gain and ceiling are corrected and it's
// tried again, TAKES times at most, and the take nearest the target is kept. Not loudnorm: its one-pass fallback missed
// -14 by up to 2 LU and the peak by 0.4 dB on test sounds, and it turned near-silence up 55 dB. A reel quieter than
// SILENT_LUFS is left as it is; one turned up more than LOUD_BOOST dB says so when it's printed, as its noise rises too.
function master(mix, tmp, on) {
  const encode = (filters, k) => {
    const file = join(tmp, `sound${k}.m4a`);
    ffmpegRun(['-hide_banner', '-loglevel', 'error', '-n', '-protocol_whitelist', 'file', ...demuxer(mix), '-i', mix, '-map', '0:a:0',
      '-af', [...filters, 'aformat=sample_fmts=fltp:channel_layouts=stereo'].join(','), '-c:a', 'aac', '-b:a', '160k', file]);
    return { file, ...loudness(file) };
  };
  if (!on) return encode([], 0);
  const before = loudness(mix);
  if (before.lufs === null || before.lufs < SILENT_LUFS) return { ...encode([], 0), before, silent: true };
  let [gain, ceiling] = [LUFS - before.lufs, TRUE_PEAK - 1];
  const takes = [];
  for (let k = 0; k < TAKES; k++) {
    const limiter = before.true_peak + gain > ceiling
      ? ['aresample=192000', `alimiter=limit=${(10 ** (ceiling / 20)).toFixed(4)}:level=false:latency=true`, 'aresample=48000'] : [];
    const take = encode([`volume=${gain.toFixed(2)}dB`, ...limiter], k);
    takes.push(take);
    if (Math.abs(take.lufs - LUFS) <= 0.2 && take.true_peak <= TRUE_PEAK) break;
    gain += LUFS - take.lufs;
    if (take.true_peak > TRUE_PEAK) ceiling -= take.true_peak - TRUE_PEAK + 0.1;
  }
  const miss = (t) => Math.abs(t.lufs - LUFS) + (t.true_peak > TRUE_PEAK ? 100 : 0);
  return { ...takes.reduce((a, b) => (miss(b) < miss(a) ? b : a)), before };
}

const taken = (path) => { try { lstatSync(path); return true; } catch { return false; } };  // a dangling link counts

function outputPath(out, root) {
  const media = join(root, BASES.media);
  if (typeof out !== 'string' || out.includes('://') || /^[a-z][a-z0-9+.-]*:/i.test(out)) throw new Error('refused: --out must be a local path');
  const target = resolve(isAbsolute(out) ? out : join(root, out));
  if (!target.toLowerCase().endsWith('.mp4') || taken(target) || taken(`${target}.json`)) {
    throw new Error(`refused: --out ${out} must be a new .mp4, with no file or link at it or at its .json`);
  }
  if (!existsSync(media)) throw new Error('refused: workspaces/marketing/media/ is missing');
  let nearest = dirname(target);
  while (!existsSync(nearest)) nearest = dirname(nearest);
  if (!within(realpathSync(nearest), realpathSync(media))) throw new Error(`refused: --out ${out} must be in ${BASES.media}/`);
  mkdirSync(dirname(target), { recursive: true });
  if (!within(realpathSync(dirname(target)), realpathSync(media))) throw new Error(`refused: --out ${out} must be in ${BASES.media}/`);
  return target;
}

export function compile(list, out, { root = REPO } = {}) {
  if (!list || !Array.isArray(list.clips) || !list.clips.length) throw new Error('refused: the edit list needs clips');
  const target = outputPath(out, root);
  const parts = segments(list.clips, list.cuts || []);
  const last = parts[parts.length - 1];
  const total = last.at + last.to - last.from;
  const look = lookFilters(list.grade, list.zooms || []);
  const crops = list.clips.map((c, i) => cropFilter(c.crop, i));
  if (list.loudness !== undefined && typeof list.loudness !== 'boolean') throw new Error('refused: loudness must be true or false');
  const clips = list.clips.map((c) => ({ ...c, ...provenance(c.file, { ai: c.ai, root }) }));
  clips.forEach((c, i) => {
    const length = IMAGE.test(c.real) ? null : probe(c.real).duration;
    if (length !== null && !(num(c.out, 'out') <= length + 0.05)) throw new Error(`refused: clips[${i}].out is past the clip's end (${length} s)`);
  });
  const overlays = (list.overlays || []).map((o, i) => {
    const [s, e] = [num(o.start ?? 0, `overlays[${i}].start`), num(o.end ?? total, `overlays[${i}].end`)];
    if (!(e > s && s >= 0)) throw new Error(`refused: overlays[${i}] needs 0 <= start < end`);
    return { ...o, start: s, end: e, x: Math.round(num(o.x ?? 0, 'x')), y: Math.round(num(o.y ?? 0, 'y')), ...provenance(o.file, { ai: o.ai, root }) };
  });
  const voice = list.voice ? { ...list.voice, ...provenance(list.voice.file, { ai: list.voice.ai, root }) } : null;
  const music = list.music ? { ...list.music, ...provenance(list.music.file, { ai: list.music.ai, root }) } : null;
  if (music && music.provenance === 'outside' && !music.music_ok) {
    throw new Error(`refused: ${music.file} isn't recorded as licensed for a music bed ("music_ok": true in its manifest entry); `
      + "use Instagram's library at publishing instead");
  }
  const sfx = (list.sfx || []).map((s, i) => {
    const [start, volume] = [num(s.start ?? 0, `sfx[${i}].start`), num(s.volume ?? 1, `sfx[${i}].volume`)];
    if (!(start >= 0 && start < total)) throw new Error(`refused: sfx[${i}].start must be inside the reel (0 to ${total.toFixed(3)} s)`);
    const effect = { ...s, start, volume, ...provenance(s.file, { ai: s.ai, root }) };
    if (!probe(effect.real).audio) throw new Error(`refused: ${effect.file} has no sound`);
    if (effect.provenance === 'outside' && !effect.music_ok) {
      throw new Error(`refused: ${effect.file} isn't recorded as licensed to bake in ("music_ok": true in its manifest entry); use a sound of ours`);
    }
    return effect;
  });

  // Subtitles: each clip's cues remapped onto the reel, plus any already in reel time.
  const cues = [];
  clips.forEach((c, i) => {
    if (!c.srt) return;
    const { real } = inputPath(c.srt, root);
    cues.push(...remapCues(parseSrt(readFileSync(real, 'utf8')), parts.filter((p) => p.clip === i)));
  });
  if (list.subtitles) cues.push(...parseSrt(readFileSync(inputPath(list.subtitles, root).real, 'utf8')).filter((c) => c.start < total));
  cues.sort((a, b) => a.start - b.start);

  const tmp = mkdtempSync(join(tmpdir(), 'mkt-compile-'));
  const fonts = cues.length ? golosFontsDir() : null;
  let sound;
  try {
    const args = ['-hide_banner', '-loglevel', 'error', '-n'];
    const input = (file, before = []) => {
      args.push(...before, '-protocol_whitelist', 'file', ...demuxer(file), '-i', file);
      return args.filter((a) => a === '-i').length - 1;
    };
    const rendered = join(tmp, 'reel.mp4');
    const graph = [];
    const runs = [];  // parts joined by hard cuts; a crossfade starts the next run
    parts.forEach((p, k) => {
      if (!k || p.fade) runs.push([]);
      runs[runs.length - 1].push(k);
      const clip = clips[p.clip];
      const length = (p.to - p.from).toFixed(3);
      const still = IMAGE.test(clip.real);
      const idx = input(clip.real, still ? ['-loop', '1', '-framerate', String(FPS), '-t', length] : ['-ss', p.from.toFixed(3), '-t', length]);
      graph.push(`[${idx}:v]${crops[p.clip]}scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},fps=${FPS},setsar=1,format=yuv420p,${SDR},setpts=PTS-STARTPTS[v${k}]`);
      const vol = num(clip.volume ?? 1, 'volume');
      graph.push(!still && probe(clip.real).audio
        ? `[${idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=${vol},apad,atrim=0:${length},asetpts=PTS-STARTPTS[a${k}]`
        : `anullsrc=channel_layout=stereo:sample_rate=48000,atrim=0:${length}[a${k}]`);
    });
    runs.forEach((run, r) => graph.push(`${run.map((k) => `[v${k}][a${k}]`).join('')}concat=n=${run.length}:v=1:a=1[vrun${r}][arun${r}]`));
    let [vcur, acat] = ['vrun0', 'arun0'];
    if (runs.length > 1) {
      // Crossfades are timed layers on a clock of the reel's length: each run fades in over the last, whose final frame
      // holds under it. Not xfade: it ends the picture once its second input has finished buffering, as a short run does.
      graph.push(`color=c=black:s=${W}x${H}:r=${FPS}:d=${total.toFixed(3)},setsar=1,format=yuv420p,${SDR}[vclock]`);
      vcur = 'vclock';
      runs.forEach((run, r) => {
        const { fade, at } = parts[run[0]];
        graph.push(`[vrun${r}]format=yuva420p${fade ? `,fade=t=in:st=0:d=${fade.toFixed(3)}:alpha=1` : ''},setpts=PTS+${at.toFixed(3)}/TB[vlayer${r}]`,
          `[${vcur}][vlayer${r}]overlay[vstack${r}]`);
        vcur = `vstack${r}`;
        if (r) {
          graph.push(`[${acat}][arun${r}]acrossfade=d=${fade.toFixed(3)}[afade${r}]`);
          acat = `afade${r}`;
        }
      });
    }
    if (look) {
      graph.push(`[${vcur}]${look}[vlook]`);
      vcur = 'vlook';
    }
    overlays.forEach((o, i) => {
      const still = IMAGE.test(o.real);
      const idx = input(o.real, still ? ['-loop', '1', '-framerate', String(FPS), '-t', total.toFixed(3)] : []);
      graph.push(`[${idx}:v]format=rgba,setpts=PTS-STARTPTS${still ? '' : `+${o.start}/TB`}[o${i}]`);
      graph.push(`[${vcur}][o${i}]overlay=${o.x}:${o.y}:eof_action=pass:enable='between(t,${o.start},${o.end})'[vo${i}]`);
      vcur = `vo${i}`;
    });
    if (cues.length) {
      const srt = join(tmp, 'reel.srt');
      writeFileSync(srt, formatSrt(cues));
      graph.push(`[${vcur}]subtitles=${escapeFilter(srt)}:fontsdir=${escapeFilter(fonts)}:force_style='${STYLE}'[vsub]`);
      vcur = 'vsub';
    }
    let speech = acat;
    if (voice) {
      const idx = input(voice.real);
      const ms = Math.round(num(voice.start ?? 0, 'voice.start') * 1000);
      graph.push(`[${idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=${num(voice.volume ?? 1, 'voice.volume')},adelay=${ms}|${ms}[voice]`);
      graph.push(`[${acat}][voice]amix=inputs=2:duration=first:normalize=0[speech]`);
      speech = 'speech';
    }
    let aout = speech;
    if (music) {
      const idx = input(music.real, ['-stream_loop', '-1']);
      graph.push(`[${idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=${num(music.volume ?? 0.2, 'music.volume')}[bed]`);
      graph.push(`[${speech}]asplit=2[sp][key]`, '[bed][key]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=400[ducked]',
        '[sp][ducked]amix=inputs=2:duration=first:normalize=0[mix]');
      aout = 'mix';
    }
    if (sfx.length) {  // after the ducking: a click shouldn't pump the music
      const effects = sfx.map((s, i) => {
        const idx = input(s.real);
        const ms = Math.round(s.start * 1000);
        graph.push(`[${idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=${s.volume},adelay=${ms}|${ms}[fx${i}]`);
        return `[fx${i}]`;
      });
      graph.push(`[${aout}]${effects.join('')}amix=inputs=${sfx.length + 1}:duration=first:normalize=0[fxmix]`);
      aout = 'fxmix';
    }
    // The picture is final here; the sound stays 32-bit float, with any overs, until it's mastered.
    const mix = join(tmp, 'mix.mov');
    args.push('-filter_complex', graph.join(';'), '-map', `[${vcur}]`, '-map', `[${aout}]`, '-t', total.toFixed(3),
      '-r', String(FPS), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'pcm_f32le', mix);
    ffmpegRun(args);
    const { file: audio, before, silent } = master(mix, tmp, list.loudness !== false);
    ffmpegRun(['-hide_banner', '-loglevel', 'error', '-n', '-protocol_whitelist', 'file', ...demuxer(mix), '-i', mix, '-protocol_whitelist', 'file',
      ...demuxer(audio), '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-movflags', '+faststart', rendered]);
    const heard = loudness(rendered);
    sound = list.loudness === false ? { ...heard, off: true } : silent ? { ...heard, silent } : { ...heard, before };
    copyFileSync(rendered, target, constants.COPYFILE_EXCL);  // never through a file or link that appeared meanwhile
  } finally {
    rmSync(tmp, { recursive: true, force: true });
    if (fonts) rmSync(fonts, { recursive: true, force: true });
  }

  // Provenance beside the reel, and the parts used in each outside clip's manifest entry.
  const clean = ({ real, ...rest }) => rest;
  const used = parts.map((p) => ({ file: clips[p.clip].file, from: +p.from.toFixed(3), to: +p.to.toFixed(3), at: +p.at.toFixed(3) }));
  const inputs = [...clips, ...overlays, ...sfx, voice, music].filter(Boolean);
  const record = {
    reel: relative(realpathSync(root), realpathSync(target)), made: new Date().toISOString(), seconds: +total.toFixed(3),
    ai_generated: inputs.some((i) => i.provenance === 'ai-generated' || i.ai_generated),
    inputs: inputs.map(clean).map(({ in: _in, out: _out, srt: _srt, ...rest }) => rest), parts: used, subtitles: cues.length,
    loudness: sound,
  };
  writeFileSync(`${target}.json`, `${JSON.stringify(record, null, 2)}\n`, { flag: 'wx' });
  for (const c of [...new Map(clips.filter((c) => c.provenance === 'outside').map((c) => [c.file, c])).values()]) {
    const path = join(root, c.manifest);
    const manifest = JSON.parse(readFileSync(path, 'utf8'));
    const entry = manifest.files.find((e) => e.sha256 === c.sha256);
    (entry.used ||= []).push(...used.filter((u) => u.file === c.file).map((u) => ({ reel: record.reel, from: u.from, to: u.to, at: record.made })));
    writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
  }
  return { out: target, record };
}

// What main and batch print for a reel built, its loudness as measured in it.
export function wrote(out, record) {
  const db = (v) => (v === null ? '-inf' : v.toFixed(1));
  const { lufs, true_peak: peak, off, silent, before } = record.loudness;
  const on = Math.abs(lufs - LUFS) <= 0.5 && peak <= TRUE_PEAK;
  const note = off ? ', loudness off' : silent ? ', silent, left as it is' : on ? '' : `, off the target of ${LUFS} LUFS and ${TRUE_PEAK} dBTP`;
  const boost = before ? lufs - before.lufs : 0;
  const loud = boost > LOUD_BOOST ? `, turned up ${boost.toFixed(1)} dB: listen for noise` : '';
  return `wrote ${out} (${record.seconds} s, ${record.parts.length} parts, ai_generated ${record.ai_generated}, `
    + `${db(lufs)} LUFS, ${db(peak)} dBTP${note}${loud}) and ${basename(out)}.json`;
}

const VARS = ['voice', 'swap', 'times', 'retime'];
const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// A retime map as a function of the old reel time: straight lines between its [old, new] points, slope 1 outside them.
function warp(map, times, where) {
  if (!Array.isArray(map) || !map.length) throw new Error(`refused: ${where}.map needs at least one [old, new] pair`);
  const points = map.map((pair, i) => {
    if (!Array.isArray(pair) || pair.length !== 2) throw new Error(`refused: ${where}.map[${i}] must be [old, new]`);
    if (typeof pair[1] === 'string' && !Object.hasOwn(times, pair[1])) throw new Error(`refused: ${where}.map[${i}]: no time named ${pair[1]}`);
    return [num(pair[0], `${where}.map[${i}][0]`), num(typeof pair[1] === 'string' ? times[pair[1]] : pair[1], `${where}.map[${i}][1]`)];
  });
  if (points.some(([o, n], i) => i && !(o > points[i - 1][0] && n > points[i - 1][1]))) throw new Error(`refused: ${where}.map must rise in both columns`);
  return (t) => {
    const k = points.findIndex(([o]) => o >= t);
    if (k <= 0) {
      const [o, n] = points[k === 0 ? 0 : points.length - 1];
      return +(n + t - o).toFixed(3);
    }
    const [[o0, n0], [o1, n1]] = [points[k - 1], points[k]];
    return +(n0 + ((t - o0) * (n1 - n0)) / (o1 - o0)).toFixed(3);
  };
}

// The --vars file, checked, with each retime map made a function.
export function readVars(path, root = REPO) {
  const vars = JSON.parse(readFileSync(inputPath(path, root).real, 'utf8'));
  if (!isObject(vars)) throw new Error(`refused: ${path} must hold one JSON object`);
  const unknown = Object.keys(vars).filter((k) => !VARS.includes(k));
  if (unknown.length) throw new Error(`refused: --vars has only ${VARS.join(', ')}, not ${unknown.join(', ')}`);
  const { voice, swap = {}, times = {}, retime } = vars;
  if (voice !== undefined && !isObject(voice)) throw new Error('refused: --vars voice must be an object, as in an edit list');
  if (!isObject(swap) || !Object.values(swap).every(isObject)) throw new Error("refused: --vars swap must map a clip's file to a clip");
  if (!isObject(times)) throw new Error('refused: --vars times must map names to seconds');
  Object.entries(times).forEach(([k, v]) => num(v, `times.${k}`));
  if (retime !== undefined && !(Array.isArray(retime) && retime.length)) throw new Error('refused: --vars retime must be a list of rules');
  const rules = retime && retime.map((rule, i) => {
    const match = isObject(rule) ? [rule.match].flat() : [];
    if (!match.length || !match.every((m) => typeof m === 'string' && m)) throw new Error(`refused: retime[${i}].match must be a part of a list's name, or a list of them`);
    const at = warp(rule.map, times, `retime[${i}]`);
    if (at(0) < 0) throw new Error(`refused: retime[${i}].map moves the reel's start before 0 (to ${at(0)})`);
    return { match, at };
  });
  return { voice, swap, rules };
}

// One edit list with the vars applied: its times moved by the first retime rule that matches its name, its clips
// swapped, its voice replaced. A clip keeps its in and gets the length of its stretch of the (moved) reel.
export function applyVars(list, name, { voice, swap = {}, rules } = {}) {
  if (!list || !Array.isArray(list.clips) || !list.clips.length) throw new Error('refused: the edit list needs clips');
  const changed = { ...list };
  let lengths = null;
  if (rules) {
    const rule = rules.find((r) => r.match.some((m) => name.includes(m)));
    if (!rule) throw new Error("refused: no retime rule matches this list's name");
    if ((list.cuts || []).length || list.subtitles || list.clips.some((c, i) => num(c.crossfade ?? 0, `clips[${i}].crossfade`))) {
      throw new Error("refused: a list with cuts, crossfades or subtitles can't be retimed");
    }
    let [old, before] = [0, 0];
    lengths = list.clips.map((c, i) => {
      old += num(c.out, `clips[${i}].out`) - num(c.in ?? 0, `clips[${i}].in`);
      const end = rule.at(old);
      const length = +(end - before).toFixed(3);
      before = end;
      return length;
    });
    const move = (item, keys) => Object.fromEntries(Object.entries(item).map(([k, v]) => [k, keys.includes(k) ? rule.at(num(v, k)) : v]));
    if (list.overlays) changed.overlays = list.overlays.map((o) => move(o, ['start', 'end']));
    if (list.zooms) changed.zooms = list.zooms.map((z) => move(z, ['start', 'end']));
    if (list.sfx) changed.sfx = list.sfx.map((s) => move(s, ['start']));
    if (list.voice) changed.voice = move(list.voice, ['start']);
  }
  changed.clips = list.clips.map((clip, i) => {
    const swapped = Object.hasOwn(swap, clip.file) ? swap[clip.file] : null;
    if (!swapped && !lengths) return clip;
    const from = num((swapped || clip).in ?? 0, `clips[${i}].in`);
    const length = lengths ? lengths[i] : num(clip.out, `clips[${i}].out`) - num(clip.in ?? 0, `clips[${i}].in`);
    return { ...(swapped || clip), in: from, out: +(from + length).toFixed(3) };
  });
  if (voice) changed.voice = { ...voice };
  return changed;
}

// Every <name>.edit.json in folder, in name order, to <dir>/<name>.mp4 through compile(). Lists are read and changed
// first, and any that can't be stop the batch; a reel that fails to build is named and the rest go on.
export function batch(folder, dir, varsFile, { root = REPO, log = () => {} } = {}) {
  if (typeof folder !== 'string' || !folder || typeof dir !== 'string' || !dir) throw new Error('refused: --batch and --dir need a folder each');
  const vars = varsFile ? readVars(varsFile, root) : {};
  const given = isAbsolute(folder) ? folder : join(root, folder);
  const full = existsSync(given) && statSync(given).isDirectory() ? realpathSync(given) : null;
  if (!full || !Object.values(BASES).some((b) => existsSync(join(root, b)) && within(full, realpathSync(join(root, b))))) {
    throw new Error(`refused: --batch ${folder} must be a folder in ${Object.values(BASES).join('/, ')}/`);
  }
  const names = readdirSync(full).filter((n) => n.endsWith('.edit.json')).sort().map((n) => n.slice(0, -'.edit.json'.length));
  if (!names.length) throw new Error(`refused: ${folder} has no .edit.json files`);
  const problems = [];
  const lists = names.map((name) => {
    try {
      const list = JSON.parse(readFileSync(inputPath(join(full, `${name}.edit.json`), root).real, 'utf8'));
      return { name, list, changed: applyVars(list, name, vars) };
    } catch (e) {
      problems.push(`${name}: ${e.message}`);
      return null;
    }
  });
  if (problems.length) throw new Error(`refused: nothing built; ${problems.length} of ${names.length} lists:\n${problems.join('\n')}`);
  for (const key of Object.keys(vars.swap || {})) {
    if (!lists.some(({ list }) => list.clips.some((c) => c.file === key))) log(`note: swap ${key} matches no clip in ${folder}`);
  }
  return lists.map(({ name, changed }) => {
    try {
      const { out, record } = compile(changed, join(dir, `${name}.mp4`), { root });
      log(wrote(out, record));
      return { name, out, record };
    } catch (e) {
      log(`${name}: ${e.message}`);
      return { name, error: e.message };
    }
  });
}

// The command line: its exit code.
export function main(args, { root = REPO, log = console.log, error = console.error } = {}) {
  const { values } = parseArgs({ args, options: { list: { type: 'string' }, out: { type: 'string' }, 'propose-cuts': { type: 'boolean' },
    batch: { type: 'string' }, dir: { type: 'string' }, vars: { type: 'string' } } });
  const single = values.list && (values.out || values['propose-cuts']) && !values.batch && !values.dir && !values.vars;
  if (!single && !(values.batch && values.dir && !values.list && !values.out && !values['propose-cuts'])) {
    error('usage: video/compile.mjs --list <edit-list.json> (--out <media/...mp4> | --propose-cuts)\n'
      + '       video/compile.mjs --batch <folder of .edit.json> --dir <media/... folder> [--vars <vars.json>]');
    return 2;
  }
  try {
    if (values.batch) {
      const failed = batch(values.batch, values.dir, values.vars, { root, log }).filter((r) => r.error);
      if (failed.length) {
        error(`${failed.length} reels not built: ${failed.map((r) => r.name).join(', ')}`);
        return 1;
      }
    } else {
      const listFile = inputPath(values.list, root).real;
      const list = JSON.parse(readFileSync(listFile, 'utf8'));
      if (values['propose-cuts']) {
        log(JSON.stringify(proposeCuts(list), null, 2));
      } else {
        const { out, record } = compile(list, values.out, { root });
        log(wrote(out, record));
      }
    }
  } catch (e) {
    error(e.message);
    return 1;
  }
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main(process.argv.slice(2));  // exitCode, not exit(): a long log through a pipe would be cut short
}
