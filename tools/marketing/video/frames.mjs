#!/usr/bin/env node
// Save frames of a video as PNGs, so a reviewer (who reads images, not video) can check it.
//
//   node video/frames.mjs --in reel.mp4 --out <folder> [--every 1] [--width 540]
//
// Writes <folder>/frame-001.png, … one frame every --every seconds (default 1), at --width px wide (default 540;
// 1080 for full-resolution stills, e.g. a cover).
// Reads only a local file: a URL is refused, and ffmpeg may open nothing but files (-protocol_whitelist file).
import { spawnSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import ffmpeg from 'ffmpeg-static';
import { demuxer } from './formats.mjs';

export function saveFrames({ input, out, every = 1, width = 540 }) {
  if (input.includes('://')) throw new Error(`refused: ${input} is a URL; frames come only from a local file`);
  if (!Number.isInteger(width) || width < 16 || width > 3840) throw new Error('refused: --width must be a whole number of pixels, 16 to 3840');
  mkdirSync(out, { recursive: true });
  const run = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file', ...demuxer(input), '-i', input,
    '-vf', `fps=1/${every},scale=${width}:-2`, join(out, 'frame-%03d.png')], { encoding: 'utf8' });
  if (run.status !== 0) throw new Error(`ffmpeg failed: ${run.stderr}`);
  return out;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { values } = parseArgs({ options: { in: { type: 'string' }, out: { type: 'string' }, every: { type: 'string', default: '1' }, width: { type: 'string', default: '540' } } });
  if (!values.in || !values.out) {
    console.error('usage: frames.mjs --in <video> --out <folder> [--every <seconds>] [--width <px>]');
    process.exit(2);
  }
  console.log(`wrote frames to ${saveFrames({ input: values.in, out: values.out, every: Number(values.every), width: Number(values.width) })}`);
}
