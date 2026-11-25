#!/usr/bin/env node
// Take apart a reel for the reel library (the swipe-teardown skill):
// a frame every 0.5 s, a frame at each scene change, and the audio track for scribe.py.
//
//   node swipe/ingest.mjs --in workspaces/marketing/sources/<brand>/<week>/<slug>/video.mp4 --out workspaces/marketing/swipe/<slug>
//
// Writes <out>/frames/frame-001.png …, <out>/scenes/scene-001.png … and <out>/audio.wav (16 kHz mono).
// It never downloads anything: footage/fetch.py downloads a link into sources/ with its MANIFEST.json, or the
// founder saves the file in swipe/ when a site refuses. So --in must be a file in workspaces/marketing/sources/ or
// swipe/, not a URL, and --out a folder in swipe/, all compared with links resolved (the swipe folder may be a link to
// a synced folder; a link inside it that points elsewhere doesn't count). ffmpeg may open nothing but files
// (-protocol_whitelist file). The video is kept, so the same file serves compilations.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import ffmpeg from 'ffmpeg-static';
import { demuxer } from '../video/formats.mjs';
import { saveFrames } from '../video/frames.mjs';

const SCENE_THRESHOLD = 0.3;
const REPO = fileURLToPath(new URL('../../..', import.meta.url));
const SWIPE = 'workspaces/marketing/swipe';
const SOURCES = 'workspaces/marketing/sources';

function run(args) {
  const result = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file', ...args],
    { encoding: 'utf8' });
  if (result.status !== 0) throw new Error(`ffmpeg failed: ${result.stderr}`);
}

// True when the real path `path` is the real folder `base` or inside it.
function within(path, base) {
  const rel = relative(base, path);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

// The reel's real path, after checking it and creating --out; throws when --in is outside sources/ and swipe/,
// or --out outside swipe/.
function checkPaths(input, out, root) {
  if (input.includes('://')) throw new Error(`refused: --in ${input} is a URL; download it with footage/fetch.py first`);
  const swipe = realpathSync(join(root, SWIPE));
  const sources = join(root, SOURCES);
  const bases = existsSync(sources) ? [swipe, realpathSync(sources)] : [swipe];
  const reel = existsSync(input) ? realpathSync(input) : null;
  if (!reel || !statSync(reel).isFile() || !bases.some((b) => within(reel, b))) {
    throw new Error(`refused: --in ${input} must be a file in ${SOURCES}/ or ${SWIPE}/`);
  }
  const outside = new Error(`refused: --out ${out} must be a folder in ${SWIPE}/`);
  const target = resolve(out);
  let nearest = target;  // the nearest folder that exists, checked before anything is created
  while (!existsSync(nearest)) nearest = dirname(nearest);
  if (!within(realpathSync(nearest), swipe)) throw outside;
  mkdirSync(target, { recursive: true });
  if (!within(realpathSync(target), swipe)) throw outside;
  return reel;
}

export function ingest({ input, out, root = REPO }) {
  const reel = checkPaths(input, out, root);
  const frames = saveFrames({ input: reel, out: join(out, 'frames'), every: 0.5 });
  const scenes = join(out, 'scenes');
  mkdirSync(scenes, { recursive: true });
  run([...demuxer(reel), '-i', reel, '-vf', `select='gt(scene,${SCENE_THRESHOLD})',scale=540:-2`, '-fps_mode', 'vfr', join(scenes, 'scene-%03d.png')]);
  const audio = join(out, 'audio.wav');
  const probe = spawnSync(ffmpeg, ['-hide_banner', '-protocol_whitelist', 'file', ...demuxer(reel), '-i', reel], { encoding: 'utf8' });
  const hasAudio = /Stream #.*Audio/.test(probe.stderr);
  if (hasAudio) run([...demuxer(reel), '-i', reel, '-vn', '-ac', '1', '-ar', '16000', audio]);
  return {
    frames: readdirSync(frames).length,
    scenes: readdirSync(scenes).length,
    audio: hasAudio ? audio : null,
  };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { values } = parseArgs({ options: { in: { type: 'string' }, out: { type: 'string' } } });
  if (!values.in || !values.out) {
    console.error('usage: swipe/ingest.mjs --in <reel in sources/ or swipe/> --out <folder in swipe/>');
    process.exit(2);
  }
  const done = ingest({ input: values.in, out: values.out });
  console.log(`${done.frames} frames, ${done.scenes} scene changes, audio: ${done.audio ?? 'none (no audio track)'}`);
}
