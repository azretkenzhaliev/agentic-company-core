#!/usr/bin/env node
// Render a Remotion composition, 1080x1920: to MP4 (H.264), or to a transparent .mov (ProRes 4444) for video/compile.mjs's overlays.
//
//   node render/reel.mjs --props reel.json --out reel.mp4 [--composition TextReel]
//   node render/reel.mjs --composition Captions --props style.json --words <name>.words.json --out captions.mov
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { bundle } from '@remotion/bundler';
import { RenderInternals, renderMedia, selectComposition } from '@remotion/renderer';

const TRANSPARENT = { codec: 'prores', proResProfile: '4444', imageFormat: 'png', pixelFormat: 'yuva444p10le' };

// Remotion 4.0.535's browser code, a fork of puppeteer, reads a page's response the moment the page loads, but holds the
// response back until Chrome's Network.responseReceivedExtraInfo for it arrives. On a busy machine that comes after the load
// now and then, and the render fails: 'Visited "http://localhost:3000/index.html" but got no response.'
// So every page Remotion opens waits for that response.
// Leans on Remotion's internals: recheck after an upgrade (the captions test renders through it).
const { newPage } = RenderInternals.HeadlessBrowser.prototype;
RenderInternals.HeadlessBrowser.prototype.newPage = async function (options) {
  const page = await newPage.call(this, options);
  const network = page.mainFrame()._frameManager.networkManager();
  const goto = page.goto.bind(page);
  page.goto = async (args) => {
    let navigation = null;
    const seen = (type, request) => {
      if (type.description === 'NetworkManager.Request' && request.isNavigationRequest() && request.frame() === page.mainFrame()) navigation = request;
    };
    network.on('*', seen);
    const deadline = Date.now() + args.timeout;
    try {
      return (await goto(args)) ?? (navigation && await responseOf(navigation, page._client(), deadline - Date.now()));
    } finally {
      network.off('*', seen);
    }
  };
  return page;
};

// The request's response once Remotion has paired it with its ExtraInfo, on whichever of the two events comes last (Remotion's
// handlers run first), or null after `timeout` ms: what's left of the navigation's own timeout.
const PAIRING = ['Network.responseReceived', 'Network.responseReceivedExtraInfo'];
const responseOf = (request, client, timeout) => new Promise((done) => {
  const finish = (response) => {
    clearTimeout(timer);
    for (const event of PAIRING) client.off(event, check);
    done(response);
  };
  const check = () => request.response() && finish(request.response());
  const timer = setTimeout(() => finish(null), timeout);
  for (const event of PAIRING) client.on(event, check);
  check();
});

export function readProps(propsFile, wordsFile) {
  const read = (file) => JSON.parse(readFileSync(resolve(file), 'utf8'));
  return wordsFile ? { ...read(propsFile), words: read(wordsFile) } : read(propsFile);
}

// `browser`: Remotion's own Chrome unless a test names another, as { browserExecutable, chromeMode }.
export async function renderReel({ props, out, composition = 'TextReel', browser = {} }) {
  out = resolve(out);
  // Remotion keeps its headless Chrome under the working directory: always tools/marketing, so there's one copy.
  process.chdir(fileURLToPath(new URL('..', import.meta.url)));
  const serveUrl = await bundle({ entryPoint: fileURLToPath(new URL('../remotion/index.jsx', import.meta.url)) });
  const comp = await selectComposition({ serveUrl, id: composition, inputProps: props, ...browser });
  const encoding = out.endsWith('.mov') ? TRANSPARENT : { codec: 'h264' };
  await renderMedia({ composition: comp, serveUrl, ...encoding, outputLocation: out, inputProps: props, ...browser });
  return out;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { values } = parseArgs({ options: { props: { type: 'string' }, out: { type: 'string' }, composition: { type: 'string' }, words: { type: 'string' } } });
  if (!values.props || !values.out) {
    console.error('usage: reel.mjs --props <file.json> --out <file.mp4|file.mov> [--composition TextReel] [--words <name>.words.json]');
    process.exit(2);
  }
  const props = readProps(values.props, values.words);
  console.log(`wrote ${await renderReel({ props, out: values.out, composition: values.composition })}`);
}
