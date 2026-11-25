#!/usr/bin/env node
// The ux-expert's browser check (README.md). For each width: a full-page screenshot, axe-core with its
// WCAG 2.2 rules switched on, and measured values. Writes <out-dir>/report.json and prints a summary.
// Usage: node tools/ux/check.mjs <url> <out-dir> [--widths 375,768,1440] [--dark] [--tabs 60] [--steps <file.mjs>]
import { chromium } from 'playwright';
import { createRequire } from 'node:module';
import { mkdirSync, realpathSync, writeFileSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const AXE_FILE = require.resolve('axe-core/axe.min.js');
const AXE_VERSION = require('axe-core/package.json').version;
const USAGE = 'usage: node tools/ux/check.mjs <url> <out-dir> [--widths 375,768,1440] [--dark] [--tabs 60] [--steps <file.mjs>]';
const SETTLE_MS = 2000; // late banners and fonts: a shift after this isn't caught

// A path with its symlinks resolved, as far as it exists.
const real = (p) => {
  try {
    return realpathSync(p);
  } catch {
    return join(real(dirname(p)), basename(p));
  }
};
// Output goes only under this repo's workspaces/ux/ (gitignored).
const UX_ROOT = real(resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'workspaces', 'ux'));

function parseArgs(argv) {
  const [url, out, ...rest] = argv;
  if (!url || !out || url.startsWith('--')) throw new Error(USAGE);
  const opts = { url, out: real(resolve(out)), widths: [375, 768, 1440], dark: false, tabs: 60, steps: null };
  const rel = relative(UX_ROOT, opts.out);
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    throw new Error(`<out-dir> must be under ${UX_ROOT}${sep}, not ${opts.out}\n${USAGE}`);
  }
  for (let i = 0; i < rest.length; i++) {
    const flag = rest[i];
    const value = () => {
      if (i + 1 >= rest.length) throw new Error(`${flag} needs a value\n${USAGE}`);
      return rest[++i];
    };
    if (flag === '--dark') opts.dark = true;
    else if (flag === '--widths') opts.widths = value().split(',').map(Number);
    else if (flag === '--tabs') opts.tabs = Number(value());
    else if (flag === '--steps') opts.steps = resolve(value());
    else throw new Error(`unknown option ${flag}\n${USAGE}`);
  }
  if (opts.widths.some((w) => !(w > 0)) || !(opts.tabs >= 0)) throw new Error(USAGE);
  return opts;
}

// Runs in the page before its own scripts: CLS (largest session window) and LCP observers, and helpers.
function init() {
  const s = (window.__ux = { cls: 0, win: 0, first: -1, last: -1, lcp: null });
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.hadRecentInput) continue;
      if (s.first < 0 || e.startTime - s.last > 1000 || e.startTime - s.first > 5000) {
        s.win = 0;
        s.first = e.startTime;
      }
      s.win += e.value;
      s.last = e.startTime;
      s.cls = Math.max(s.cls, s.win);
    }
  }).observe({ type: 'layout-shift', buffered: true });
  new PerformanceObserver((list) => {
    const e = list.getEntries().at(-1);
    if (e) s.lcp = e.startTime;
  }).observe({ type: 'largest-contentful-paint', buffered: true });
  window.__uxName = (el) => {
    const id = el.id ? `#${el.id}` : '';
    const cls = el.classList.length ? `.${[...el.classList].join('.')}` : '';
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || '').trim().slice(0, 40);
    return `${el.tagName.toLowerCase()}${id}${cls}${label ? ` "${label}"` : ''}`;
  };
  window.__uxStyle = (el) => {
    const c = getComputedStyle(el);
    return {
      outline: `${c.outlineStyle} ${c.outlineWidth} ${c.outlineColor}`,
      boxShadow: c.boxShadow,
      border: c.borderTopColor,
      background: c.backgroundColor,
      color: c.color,
      underline: c.textDecorationLine,
    };
  };
}

function measure() {
  const text = document.body ? document.body.innerText : '';
  const words = text.split(/[^\p{L}]+/u);
  const mixed = [...new Set(words.filter((w) => /[A-Za-z]/.test(w) && /[Ѐ-ӿ]/.test(w)))];
  const cyr = (text.match(/[Ѐ-ӿ]/g) || []).length;
  const lat = (text.match(/[A-Za-z]/g) || []).length;
  const html = document.documentElement;
  const viewport = document.querySelector('meta[name="viewport"]');
  return {
    lang: html.getAttribute('lang'),
    cyrillicShare: cyr + lat ? Math.round((100 * cyr) / (cyr + lat)) / 100 : null,
    mixedScriptWords: mixed.slice(0, 50),
    overflowX: html.scrollWidth - html.clientWidth,
    viewportMeta: viewport ? viewport.getAttribute('content') : null,
    clsLab: Math.round(window.__ux.cls * 1000) / 1000,
    lcpLabMs: window.__ux.lcp === null ? null : Math.round(window.__ux.lcp),
  };
}

// Clickable-looking elements that Tab can't reach: an onclick, a widget role or a pointer cursor,
// with no native focus and no tabindex >= 0 (outermost element only).
function unreachable() {
  const focusable = 'a[href],button,input,select,textarea,summary,label,[contenteditable],[tabindex]:not([tabindex="-1"])';
  const roles = ['button', 'link', 'radio', 'checkbox', 'tab', 'menuitem', 'option', 'switch'];
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (out.length >= 50) break;
    if (!el.getClientRects().length || el.closest(focusable)) continue;
    const pointer = getComputedStyle(el).cursor === 'pointer';
    const parentPointer = el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer';
    if (el.hasAttribute('onclick') || roles.includes(el.getAttribute('role')) || (pointer && !parentPointer)) {
      out.push(window.__uxName(el));
    }
  }
  return out;
}

async function tabWalk(page, max) {
  await page.evaluate(() => {
    if (document.activeElement) document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  const stops = [];
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate((n) => {
      const el = document.activeElement;
      if (!el || el === document.body || el.hasAttribute('data-ux-tab')) return null;
      el.setAttribute('data-ux-tab', String(n));
      const r = el.getBoundingClientRect();
      return { n, el: window.__uxName(el), size: [Math.round(r.width), Math.round(r.height)], focused: window.__uxStyle(el) };
    }, i);
    if (!stop) break;
    stops.push(stop);
  }
  // Each stop by its own tag: Tab order isn't document order (a positive tabindex, for one).
  const unfocused = await page.evaluate((ns) => {
    if (document.activeElement) document.activeElement.blur();
    return ns.map((n) => window.__uxStyle(document.querySelector(`[data-ux-tab="${n}"]`)));
  }, stops.map((stop) => stop.n));
  return stops.map((stop, i) => {
    const changed = Object.keys(stop.focused).filter((k) => stop.focused[k] !== unfocused[i][k]);
    return { n: stop.n, el: stop.el, size: stop.size, indicator: changed.length ? changed : 'none' };
  });
}

async function runAxe(page) {
  await page.addScriptTag({ path: AXE_FILE });
  return page.evaluate(async () => {
    const ids = window.axe.getRules(['wcag22a', 'wcag22aa']).map((r) => r.ruleId);
    const lists = ['violations', 'passes', 'incomplete', 'inapplicable'];
    const ran = (res) => ids.filter((id) => lists.some((k) => res[k].some((r) => r.id === id)));
    const byDefault = ran(await window.axe.run(document));
    const on = await window.axe.run(document, { rules: Object.fromEntries(ids.map((id) => [id, { enabled: true }])) });
    return {
      wcag22RuleIds: ids,
      wcag22RanByDefault: byDefault,
      wcag22RanWhenOn: ran(on),
      violations: on.violations.map((r) => ({
        id: r.id,
        impact: r.impact,
        tags: r.tags.filter((t) => t.startsWith('wcag') || t === 'best-practice'),
        help: r.help,
        count: r.nodes.length,
        nodes: r.nodes.slice(0, 20).map((n) => ({ target: n.target.join(' '), summary: n.failureSummary })),
      })),
      incomplete: on.incomplete.map((r) => ({ id: r.id, help: r.help, count: r.nodes.length })),
    };
  });
}

async function checkOne(browser, opts, width, scheme, steps) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
  const page = await context.newPage();
  await page.addInitScript(init);
  await page.goto(opts.url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(SETTLE_MS);
  if (steps) await steps(page, { width, scheme });
  const name = `${width}${scheme === 'dark' ? '-dark' : ''}`;
  const screenshot = join(opts.out, `${name}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  const measured = await page.evaluate(measure);
  const axe = await runAxe(page);
  const notReachable = await page.evaluate(unreachable);
  const tabStops = await tabWalk(page, opts.tabs);
  await context.close();
  return { width, scheme, screenshot, ...measured, axe, tabStops, notReachable };
}

function summary(run) {
  const v = run.axe.violations.map((r) => `${r.id}(${r.count})`).join(' ') || 'none';
  const bare = run.tabStops.filter((s) => s.indicator === 'none').length;
  return [
    `${run.width}${run.scheme === 'dark' ? ' dark' : ''}: axe ${v}; incomplete ${run.axe.incomplete.length}`,
    `  CLS ${run.clsLab} (lab) · LCP ${run.lcpLabMs} ms (lab) · overflowX ${run.overflowX}px · lang ${run.lang} · cyrillic ${run.cyrillicShare} · mixed-script words ${run.mixedScriptWords.length}`,
    `  tab stops ${run.tabStops.length}, ${bare} with no focus change · clickable but not reachable by Tab ${run.notReachable.length}`,
  ].join('\n');
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const steps = opts.steps ? (await import(pathToFileURL(opts.steps).href)).default : null;
  if (opts.steps && typeof steps !== 'function') {
    throw new Error(`${opts.steps} has no default function: export default async (page, { width, scheme }) => {}`);
  }
  mkdirSync(opts.out, { recursive: true });
  const browser = await chromium.launch();
  const runs = [];
  try {
    for (const width of opts.widths) {
      for (const scheme of opts.dark ? ['light', 'dark'] : ['light']) {
        runs.push(await checkOne(browser, opts, width, scheme, steps));
      }
    }
  } finally {
    await browser.close();
  }
  const first = runs[0].axe;
  const report = {
    url: opts.url,
    checkedAt: new Date().toISOString(),
    axe: { version: AXE_VERSION, wcag22RuleIds: first.wcag22RuleIds, wcag22RanByDefault: first.wcag22RanByDefault, wcag22RanWhenOn: first.wcag22RanWhenOn },
    runs,
  };
  writeFileSync(join(opts.out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`axe-core ${AXE_VERSION}: WCAG 2.2 rules ${first.wcag22RuleIds.join(', ') || 'none'}; run by default: ${first.wcag22RanByDefault.join(', ') || 'none'}; run here: ${first.wcag22RanWhenOn.join(', ') || 'none'}`);
  for (const run of runs) console.log(summary(run));
  console.log(`report: ${join(opts.out, 'report.json')}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
