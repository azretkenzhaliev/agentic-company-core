// Apple Vision's text recognizer (macOS only), for measure/ocr.py.
// osascript -l JavaScript vision_ocr.js <languages, comma-separated> <correct|plain> <image>...
// One JSON line per image: {file, ok, items: [{text, conf, box: [x, y, width, height]}]}, the box as shares of the
// image from its top left. Local files only; ASCII out, so no locale can garble it.
ObjC.import('Vision');

function read(path, languages, correct) {
  const handler = $.VNImageRequestHandler.alloc.initWithURLOptions($.NSURL.fileURLWithPath(path), $({}));
  const request = $.VNRecognizeTextRequest.alloc.init;
  request.recognitionLevel = 0;
  request.usesLanguageCorrection = correct;
  request.recognitionLanguages = $(languages);
  if (!handler.performRequestsError($([request]), null)) return {file: path, ok: false, items: []};
  const results = request.results;
  const items = [];
  for (let i = 0; i < results.count; i++) {
    const observation = results.objectAtIndex(i);
    const candidates = observation.topCandidates(1);
    if (!candidates.count) continue;
    const top = candidates.objectAtIndex(0);
    const box = observation.boundingBox;
    items.push({text: top.string.js, conf: top.confidence,
                box: [box.origin.x, 1 - box.origin.y - box.size.height, box.size.width, box.size.height]});
  }
  return {file: path, ok: true, items: items};
}

function run(argv) {
  const languages = argv[0].split(',');
  const correct = argv[1] === 'correct';
  return argv.slice(2).map(path => JSON.stringify(read(path, languages, correct))
    .replace(/[\u007f-￿]/g, c => '\\u' + ('000' + c.charCodeAt(0).toString(16)).slice(-4))).join('\n');
}
