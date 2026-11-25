#!/usr/bin/env node
// Burn an SRT onto a clip with ffmpeg's libass, in Golos Text, above Instagram's bottom UI.
//
//   node video/subtitles.mjs --in clip.mov --srt subs.srt --out reel.mp4
//
// Local files only: a URL is refused, and ffmpeg may open nothing but files (-protocol_whitelist file).
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import ffmpeg from 'ffmpeg-static';
import { fontDir } from '../render/fonts.mjs';
import { demuxer } from './formats.mjs';

// ASS units on SRT's default 288-line canvas: size 12 is about 80 px on a 1920 px reel; margin 64 is about 430 px.
export const STYLE = 'FontName=Golos Text,FontSize=12,Bold=1,Outline=2,Shadow=0,MarginV=64,Alignment=2';

export const escapeFilter = (path) => path.replace(/\\/g, '\\\\').replace(/:/g, '\\:').replace(/'/g, "\\'");

// libass reads WOFF but not WOFF2, so give it a folder of the WOFF files only. The caller removes it.
export function golosFontsDir() {
  const fonts = mkdtempSync(join(tmpdir(), 'mkt-fonts-'));
  for (const file of readdirSync(fontDir('Golos Text')).filter((f) => f.endsWith('.woff'))) {
    symlinkSync(join(fontDir('Golos Text'), file), join(fonts, file));
  }
  return fonts;
}

export function burnSubtitles({ input, srt, out }) {
  const url = [input, srt, out].find((path) => path.includes('://'));
  if (url) throw new Error(`refused: ${url} is a URL; subtitles take and write only local files`);
  const fonts = golosFontsDir();
  try {
    const filter = `subtitles=${escapeFilter(resolve(srt))}:fontsdir=${escapeFilter(fonts)}:force_style='${STYLE}'`;
    const run = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-protocol_whitelist', 'file', ...demuxer(input), '-i', input,
      '-vf', filter, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'copy', out], { encoding: 'utf8' });
    if (run.status !== 0) throw new Error(`ffmpeg failed: ${run.stderr}`);
    return out;
  } finally {
    rmSync(fonts, { recursive: true, force: true });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { values } = parseArgs({ options: { in: { type: 'string' }, srt: { type: 'string' }, out: { type: 'string' } } });
  if (!values.in || !values.srt || !values.out) {
    console.error('usage: subtitles.mjs --in <clip> --srt <file.srt> --out <file.mp4>');
    process.exit(2);
  }
  console.log(`wrote ${burnSubtitles({ input: values.in, srt: values.srt, out: values.out })}`);
}
