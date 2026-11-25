// Fonts for renders, from @fontsource (SIL Open Font License), as @font-face CSS with absolute
// file URLs so any page on disk can use them.
// FAMILIES: the vetted fonts; content_lint allows only these. Montserrat and Golos Text for Latin
// and Cyrillic; Scheherazade New for Arabic script only. A language they don't cover needs another family here, from
// @fontsource, with the Board's yes, and in content_lint.py.
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const NODE_MODULES = fileURLToPath(new URL('../node_modules/', import.meta.url));
export const FAMILIES = {
  'Montserrat': '@fontsource/montserrat',
  'Golos Text': '@fontsource/golos-text',
  'Scheherazade New': '@fontsource/scheherazade-new',
};
export const WEIGHTS = [400, 500, 600, 700, 800];
// The Arabic font covers Arabic code points only, so its Latin letters and digits never win over the
// vetted fonts. Its subset file has Latin glyphs too, so the limit is a unicode-range.
const SUBSETS = { 'Scheherazade New': 'arabic-' };
const RANGES = { 'Scheherazade New': 'U+0600-06FF, U+0750-077F, U+08A0-08FF, U+FB50-FDFF, U+FE70-FEFF, U+200C-200F' };

export function fontDir(family) {
  return `${NODE_MODULES}${FAMILIES[family]}/files`;
}

export function fontFaceCss() {
  let css = '';
  for (const family of Object.keys(FAMILIES)) {
    const files = pathToFileURL(fontDir(family)).href;
    for (const weight of WEIGHTS) {
      const sheet = `${NODE_MODULES}${FAMILIES[family]}/${SUBSETS[family] ?? ''}${weight}.css`;
      if (!existsSync(sheet)) continue;
      let face = readFileSync(sheet, 'utf8').replaceAll('url(./files/', `url(${files}/`);
      if (RANGES[family]) face = face.replaceAll('font-display: swap;', `font-display: swap;\n  unicode-range: ${RANGES[family]};`);
      css += face;
    }
  }
  return css;
}
