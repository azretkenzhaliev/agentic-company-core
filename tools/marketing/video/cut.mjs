#!/usr/bin/env node
// Cut a clip from the founder's footage or our media, for a reel: the one ffmpeg job marketing agents run
// by hand. Bare ffmpeg isn't on their Bash list, because its filters and extra outputs can write anywhere.
//
//   node video/cut.mjs --in workspaces/marketing/inbox/<clip>.mov --out workspaces/marketing/media/<...>/cut.mp4 \
//     --start 12.5 --duration 8
//
// --in must be a file in workspaces/marketing/ (inbox/, media/ or swipe/, which may be links to a synced folder);
// --out a new .mp4 in workspaces/marketing/media/. Both are compared with links resolved; ffmpeg opens files only.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import ffmpeg from 'ffmpeg-static';
import { demuxer } from './formats.mjs';

const REPO = fileURLToPath(new URL('../../..', import.meta.url));
const SOURCES = ['workspaces/marketing', 'workspaces/marketing/inbox', 'workspaces/marketing/media', 'workspaces/marketing/swipe'];

function within(path, base) {
  const rel = relative(base, path);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

function realFolders(root, folders) {
  return folders.map((f) => join(root, f)).filter(existsSync).map((f) => realpathSync(f));
}

export function cut({ input, out, start, duration, root = REPO }) {
  if ([input, out].some((p) => p.includes('://') || /^[a-z]+:/i.test(p))) throw new Error('refused: files only, no URLs or protocols');
  const source = existsSync(input) ? realpathSync(input) : null;
  if (!source || !statSync(source).isFile() || !realFolders(root, SOURCES).some((f) => within(source, f))) {
    throw new Error(`refused: --in ${input} must be a file in workspaces/marketing/`);
  }
  const media = realpathSync(join(root, 'workspaces/marketing/media'));
  const target = resolve(out);
  if (!target.toLowerCase().endsWith('.mp4') || existsSync(target)) throw new Error(`refused: --out ${out} must be a new .mp4`);
  let nearest = dirname(target);
  while (!existsSync(nearest)) nearest = dirname(nearest);
  if (!within(realpathSync(nearest), media)) throw new Error(`refused: --out ${out} must be in workspaces/marketing/media/`);
  mkdirSync(dirname(target), { recursive: true });
  if (!within(realpathSync(dirname(target)), media)) throw new Error(`refused: --out ${out} must be in workspaces/marketing/media/`);
  const [from, length] = [Number(start), Number(duration)];
  if (!(from >= 0) || !(length > 0 && length <= 90)) throw new Error('refused: --start >= 0 and 0 < --duration <= 90 seconds');
  const run = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-n', '-protocol_whitelist', 'file',
    '-ss', String(from), ...demuxer(source), '-i', source, '-t', String(length), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', target],
  { encoding: 'utf8' });
  if (run.status !== 0) throw new Error(`ffmpeg failed: ${run.stderr}`);
  return target;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { values } = parseArgs({ options: { in: { type: 'string' }, out: { type: 'string' }, start: { type: 'string', default: '0' }, duration: { type: 'string' } } });
  if (!values.in || !values.out || !values.duration) {
    console.error('usage: video/cut.mjs --in <clip> --out <media/...mp4> --start <s> --duration <s>');
    process.exit(2);
  }
  console.log(`wrote ${cut({ input: values.in, out: values.out, start: values.start, duration: values.duration })}`);
}
