#!/usr/bin/env node
// HTML/CSS to PNG with Playwright (Chromium), with the vetted fonts and templates/base.css injected.
//
//   node render/png.mjs --html slide.html --out slide.png --size 1080x1350
//   node render/png.mjs --dir workspaces/marketing/media/founder/demo/2026-W05/wed-carousel --size 1080x1350
//   node render/png.mjs --html overlay.html --out title.png --size 1080x1920 --transparent   # an overlay for video/compile.mjs
//   node render/png.mjs --html option.html --list renders.json --dir <folder> --size 1080x1350
//
// --dir renders every *.html in the folder to a .png beside it, in name order.
// --list renders one template once per entry of a JSON list, [{ "out": "<name>.png", "values": { … } }], into --dir.
// Each entry gets a fresh page whose scripts find its values in window.VALUES; the template's relative paths count
// from where the template is. An out is a plain file name. A bad entry fails alone; the rest still render.
import { existsSync, lstatSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { chromium } from 'playwright';
import { FAMILIES, fontFaceCss } from './fonts.mjs';

// Text may only be in these families.
const ALLOWED_FAMILIES = Object.keys(FAMILIES);
export const SIZES = { '1080x1350': 'feed 4:5', '1080x1920': 'story or reel 9:16', '1080x1080': 'square 1:1' };
const BASE_CSS = readFileSync(fileURLToPath(new URL('../templates/base.css', import.meta.url)), 'utf8');

function parseSize(size) {
  if (!(size in SIZES)) throw new Error(`size must be one of ${Object.keys(SIZES).join(', ')}, not ${size}`);
  const [width, height] = size.split('x').map(Number);
  return { width, height };
}

async function withBrowser(browser, fn) {
  const own = !browser;
  browser ??= await chromium.launch();
  try {
    return await fn(browser);
  } finally {
    if (own) await browser.close();
  }
}

export async function renderPng({ html, out, size = '1080x1350', browser, transparent = false, values }) {
  const viewport = parseSize(size);
  return withBrowser(browser, async (b) => {
    const page = await b.newPage({ viewport, deviceScaleFactor: 1 });
    try {
      if (values !== undefined) await page.addInitScript((v) => { window.VALUES = v; }, values);
      // Only local files: no remote images or fonts (our own visuals; nothing renders in a system font by accident).
      await page.route('**/*', (route) => (/^(file|data):/.test(route.request().url()) ? route.continue() : route.abort()));
      await page.goto(pathToFileURL(resolve(html)).href);
      await page.addStyleTag({ content: fontFaceCss() + BASE_CSS });
      const problems = await page.evaluate(async (allowed) => {
        const bad = new Set();
        const used = new Map();
        for (const el of document.querySelectorAll('body, body *')) {
          const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
          if (!text) continue;
          const style = getComputedStyle(el);
          const first = style.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
          if (!allowed.includes(first)) { bad.add(`"${text.slice(0, 20)}" is in ${first}`); continue; }
          const font = `${style.fontWeight} 16px "${first}"`;
          used.set(font, (used.get(font) || '') + text);
        }
        for (const [font, text] of used) {
          await document.fonts.load(font, text);
          if (!document.fonts.check(font, text)) bad.add(`${font} didn't load for "${text.slice(0, 20)}"`);
        }
        await document.fonts.ready;
        return [...bad];
      }, ALLOWED_FAMILIES);
      if (problems.length) throw new Error(`fonts: ${problems.join('; ')}`);
      await page.screenshot({ path: out, clip: { x: 0, y: 0, ...viewport }, omitBackground: transparent });
      return out;
    } finally {
      await page.close().catch(() => {});  // a failed entry's page too, so a list goes on with nothing left open; a close error never hides the render's
    }
  });
}

const OUT_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*\.png$/;

// Why an entry can't render, or null; seen holds the outs before it, case-folded as the Mac's disk is.
function entryProblem(entry, dir, seen) {
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) return 'an entry is an object { "out", "values" }';
  const extra = Object.keys(entry).find((k) => k !== 'out' && k !== 'values');
  if (extra !== undefined) return `unknown key ${JSON.stringify(extra)}`;
  if (typeof entry.out !== 'string' || !OUT_NAME.test(entry.out)) return 'out is a plain file name ending in .png (letters, digits, . _ -)';
  if ('values' in entry && (entry.values === null || typeof entry.values !== 'object' || Array.isArray(entry.values))) return 'values is an object';
  if (seen.has(entry.out.toLowerCase())) return `out repeats an earlier entry's (${entry.out})`;
  seen.add(entry.out.toLowerCase());
  if (lstatSync(join(dir, entry.out), { throwIfNoEntry: false })?.isSymbolicLink()) return `${entry.out} is a link`;
  return null;
}

// Renders html once per entry into dir; returns the files written and the entries that failed, with why.
export async function renderList({ html, list, dir, size = '1080x1350', browser, transparent = false }) {
  parseSize(size);
  if (!Array.isArray(list) || !list.length) throw new Error('the list is a non-empty JSON array of { "out", "values" }');
  if (!existsSync(html) || !statSync(html).isFile()) throw new Error(`no template ${html}`);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) throw new Error(`no folder ${dir}`);
  const written = [];
  const failed = [];
  const seen = new Set();
  await withBrowser(browser, async (b) => {
    for (const [index, entry] of list.entries()) {
      const name = typeof entry?.out === 'string' ? entry.out : null;
      try {
        const problem = entryProblem(entry, dir, seen);
        if (problem) throw new Error(problem);
        written.push(await renderPng({ html, out: join(dir, entry.out), size, browser: b, transparent, values: entry.values }));
      } catch (e) {
        failed.push({ index, out: name, error: e.message.split('\n')[0] });
      }
    }
  });
  return { written, failed };
}

// For each family: does a loaded face cover the text, and does the text render
// differently from a monospace fallback (so it isn't silently a system font)?
export async function fontCoverage(families, text, { browser } = {}) {
  return withBrowser(browser, async (b) => {
    const page = await b.newPage();
    const blank = join(mkdtempSync(join(tmpdir(), 'mkt-fonts-')), 'blank.html');
    writeFileSync(blank, '<!doctype html><html><body></body></html>');
    await page.goto(pathToFileURL(blank).href);  // a file:// page may load the file:// fonts; about:blank may not
    await page.addStyleTag({ content: fontFaceCss() });
    const result = await page.evaluate(async ({ families, text }) => {
      const out = {};
      const ctx = document.createElement('canvas').getContext('2d');
      for (const family of families) {
        const faces = await document.fonts.load(`700 48px "${family}"`, text);
        ctx.font = `700 48px "${family}", monospace`;
        const withFont = ctx.measureText(text).width;
        ctx.font = '700 48px monospace';
        out[family] = { faces: faces.length, differsFromFallback: withFont !== ctx.measureText(text).width };
      }
      return out;
    }, { families, text });
    await page.close();
    return result;
  });
}

async function main() {
  const { values } = parseArgs({
    options: { html: { type: 'string' }, out: { type: 'string' }, dir: { type: 'string' }, list: { type: 'string' }, size: { type: 'string', default: '1080x1350' }, transparent: { type: 'boolean', default: false } },
  });
  if (values.list !== undefined) {
    if (!values.html || !values.dir || values.out) {
      console.error('usage: png.mjs --html <template> --list <list.json> --dir <folder> [--size …] [--transparent] (no --out: each entry names its file)');
      process.exit(2);
    }
    let list;
    try {
      list = JSON.parse(readFileSync(values.list, 'utf8'));
    } catch {
      console.error(`${values.list} isn't a readable JSON file`);
      process.exit(2);
    }
    let written, failed;
    try {
      ({ written, failed } = await renderList({ html: values.html, list, dir: values.dir, size: values.size, transparent: values.transparent }));
    } catch (e) {
      console.error(e.message.split('\n')[0]);  // a bad list, template, folder or size: nothing rendered
      process.exit(2);
    }
    for (const f of failed) console.error(`failed entry ${f.index}${f.out ? ` (${f.out})` : ''}: ${f.error}`);
    console.log(`wrote ${written.length} of ${list.length} into ${values.dir}`);
    if (failed.length) process.exitCode = 1;
  } else if (values.dir) {
    const files = readdirSync(values.dir).filter((f) => f.endsWith('.html')).sort();
    await withBrowser(null, async (browser) => {
      for (const f of files) {
        const out = join(values.dir, f.replace(/\.html$/, '.png'));
        await renderPng({ html: join(values.dir, f), out, size: values.size, browser, transparent: values.transparent });
        console.log(`wrote ${out}`);
      }
    });
  } else if (values.html && values.out) {
    console.log(`wrote ${await renderPng(values)}`);
  } else {
    console.error('usage: png.mjs --html <file> --out <png> [--size 1080x1350] [--transparent] | --dir <folder> [--size …] | --html <template> --list <list.json> --dir <folder> [--size …]');
    process.exit(2);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) await main();
