// The trial page: one screen a trial, from the design build.py wrote into the page. Nothing starts chosen. Answers save
// on this device after every trial; Save answers downloads every answer, with the design and seed, as one JSON file.
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const design = JSON.parse(document.getElementById('design').textContent);
  const { page, session } = root.dataset;
  const KEY = 'taste-trial-' + page + '-' + session + '-' + design.design_id;
  const $ = (id) => document.getElementById(id);
  const screen = $('screen');

  // Every screen in order: the welcome, each part's intro (where it has one) and its trials, the end.
  const steps = [{ kind: 'welcome' }];
  for (const part of design.parts) {
    if (part.intro.length) steps.push({ kind: 'intro', part });
    part.trials.forEach((trial, place) => steps.push({ kind: 'trial', part, trial, place }));
  }
  steps.push({ kind: 'end' });
  const trialIds = steps.filter((step) => step.kind === 'trial').map((step) => step.trial.id);
  const byId = (list) => Object.fromEntries((list || []).map((entry) => [entry.id, entry]));
  const items = Object.fromEntries(design.parts.map((part) => [part.id, byId(part.items)]));
  const dimensions = Object.fromEntries(design.parts.map((part) => [part.id, byId(part.dimensions)]));

  let state = {
    at: 0, where: 'welcome', answers: {}, intros: {}, part_seconds: {}, breaks: [], since_break: 0, total_seconds: 0,
    judging_seconds: 0, skip_intros: false, on_break: false,
  };
  let saving = true;
  let shownAt = Date.now();
  let lastActive = Date.now();

  // Where he is goes in by the screen's name, not its number, so an intro added to a part doesn't move him.
  const nameOf = (step) => (step.kind === 'trial' ? step.trial.id : step.kind + (step.part ? ':' + step.part.id : ''));

  function save() {
    state.where = nameOf(steps[state.at]);
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
      saving = true;
    } catch (e) {
      saving = false;
    }
    $('saved').textContent = saving ? 'Saved on this device after every trial.' : 'This viewer can\'t save. Press Save answers before you close it.';
    $('saved').classList.toggle('ok', saving);
    $('done').textContent = trialIds.filter((id) => id in state.answers).length;
  }

  function restore() {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(KEY));
    } catch (e) {
      saving = false;
    }
    if (saved && typeof saved === 'object') state = { ...state, ...saved };
    state.at = Math.max(0, steps.findIndex((step) => nameOf(step) === state.where));
  }

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, cls, action) => {
    const node = el('button', cls, text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  };
  const minutes = (seconds) => Math.floor(seconds / 60);

  function media(file, caption) {
    const figure = el('figure', 'media');
    let node;
    if (file.media === 'video') {
      node = document.createElement('video');
      node.muted = true;
      node.loop = true;
      node.autoplay = true;
      node.playsInline = true;
      node.controls = true;
      node.preload = 'metadata';
    } else {
      node = document.createElement('img');
      node.alt = caption || 'An option';
      node.className = 'zoomable';
    }
    node.addEventListener('error', () => figure.replaceChildren(el('p', 'missing', 'This file didn\'t load: ' + file.src)));
    node.src = file.src;
    figure.append(node);
    if (caption) figure.append(el('figcaption', '', caption));
    return figure;
  }

  function answer(value) {
    const { trial } = steps[state.at];
    const before = state.answers[trial.id];
    state.answers[trial.id] = { ...value, ms: Date.now() - shownAt, at: new Date().toISOString(), ...(before ? { revised: true } : {}) };
    go(state.at + 1);
  }

  function go(target) {
    const step = Math.sign(target - state.at) || 1;
    let n = Math.max(0, Math.min(steps.length - 1, target));
    while (steps[n].kind === 'intro' && state.skip_intros && n > 0 && n < steps.length - 1) {
      if (!(steps[n].part.id in state.intros)) state.intros[steps[n].part.id] = { skipped: true };
      n += step;
    }
    if (steps[n].kind === 'trial' && n > state.at && state.since_break >= design.break_minutes * 60) state.on_break = true;
    state.at = n;
    save();
    render();
  }

  // One row of options to pick one from, by its button or by pressing its number. A row whose media are tall (2:3
  // or taller, as stories and reels are) is marked so, by each file's own shape, so a phone shows three of them in
  // one row.
  function single(options, mine, pick) {
    const row = el('div', 'choices n' + options.length);
    const shape = ({ target }) => {
      const [width, height] = target.tagName === 'VIDEO' ? [target.videoWidth, target.videoHeight] : [target.naturalWidth, target.naturalHeight];
      if (width > 0 && height >= 1.5 * width) row.classList.add('tall');
    };
    options.forEach(({ key, file, caption }, place) => {
      const box = el('div', 'option' + (mine === key ? ' mine' : ''));
      const figure = media(file, caption);
      figure.querySelector('img, video').addEventListener(file.media === 'video' ? 'loadedmetadata' : 'load', shape);
      box.append(figure);
      const choose = button(String(place + 1) + '. This one', 'pick', () => pick(key));
      choose.dataset.key = String(place + 1);
      box.append(choose);
      row.append(box);
    });
    return row;
  }

  // Toggles: the option's buttons, each on or off; `update` runs after every press.
  function toggle(text, on, press) {
    const node = button(text, 'flip' + (on ? ' on' : ''), () => press(node));
    node.setAttribute('aria-pressed', on ? 'true' : 'false');
    return node;
  }

  const next = (text, enabled, action) => {
    const node = button(text, 'next', action);
    node.disabled = !enabled;
    return node;
  };

  // A run of steps or values: the fine ones must be one run, and the best, if any, one of them.
  function runOf(fine, count) {
    const on = [...Array(count).keys()].filter((k) => fine.has(k));
    return on.length && on[on.length - 1] - on[0] + 1 === on.length ? on : null;
  }

  const draw = {
    pairwise(part, trial, done) {
      return single(trial.items.map((id) => ({ key: id, file: items[part.id][id], caption: items[part.id][id].label })),
        done && done.pick, (pick) => answer({ pick }));
    },
    cbc(part, trial, done) {
      const levelText = (levels) => part.attributes.map((attribute) => attribute.name + ': '
        + attribute.levels.find((level) => level.id === levels[attribute.id]).label).join('. ');
      return single(trial.options.map((option, place) => ({
        key: place + 1, file: option, caption: part.show_levels ? levelText(option.levels) : '',
      })), done && done.pick, (pick) => answer({ pick }));
    },
    maxdiff(part, trial, done) {
      let best = done ? done.best : null;
      let worst = done ? done.worst : null;
      const wrap = el('div');
      const row = el('div', 'choices n4');
      const go = next('Next', false, () => answer({ best, worst }));
      const update = () => {
        for (const box of row.children) {
          const [b, w] = box.querySelectorAll('.flip');
          b.classList.toggle('on', box.dataset.id === best);
          w.classList.toggle('on', box.dataset.id === worst);
          b.setAttribute('aria-pressed', String(box.dataset.id === best));
          w.setAttribute('aria-pressed', String(box.dataset.id === worst));
        }
        go.disabled = !(best && worst && best !== worst);
      };
      for (const id of trial.items) {
        const box = el('div', 'option' + (done && (done.best === id || done.worst === id) ? ' mine' : ''));
        box.dataset.id = id;
        box.append(media(items[part.id][id], items[part.id][id].label));
        const both = el('div', 'flips');
        both.append(toggle('Best', false, () => { best = id; if (worst === id) worst = null; update(); }),
          toggle('Worst', false, () => { worst = id; if (best === id) best = null; update(); }));
        box.append(both);
        row.append(box);
      }
      wrap.append(row, go);
      update();
      return wrap;
    },
    sequence(part, trial, done) {
      const dimension = dimensions[part.id][trial.dimension];
      const order = [...Array(dimension.steps.length).keys()];
      if (trial.order === 'down') order.reverse();
      let best = done ? done.best - 1 : null;
      const fine = new Set(done ? [...Array(done.to - done.from + 1).keys()].map((k) => k + done.from - 1) : []);
      const wrap = el('div');
      wrap.append(el('h2', 'dimension', dimension.name));
      const row = el('div', 'choices steps');
      const hint = el('p', 'hint');
      const go = next('Next', false, () => {
        const run = runOf(fine, order.length);
        answer({ best: best + 1, from: run[0] + 1, to: run[run.length - 1] + 1 });
      });
      const update = () => {
        for (const box of row.children) {
          const k = Number(box.dataset.step);
          const [b, f] = box.querySelectorAll('.flip');
          b.classList.toggle('on', best === k);
          f.classList.toggle('on', fine.has(k));
          b.setAttribute('aria-pressed', String(best === k));
          f.setAttribute('aria-pressed', String(fine.has(k)));
        }
        const run = runOf(fine, order.length);
        go.disabled = !(run && best !== null && fine.has(best));
        hint.textContent = fine.size && !run ? 'The fine steps must be one run, with no gaps.' : 'Pick the best step, and every step you\'d accept.';
      };
      for (const k of order) {
        const box = el('div', 'option');
        box.dataset.step = String(k);
        box.append(media(dimension.steps[k], dimension.labels ? dimension.labels[k] : 'Step ' + (k + 1)));
        const both = el('div', 'flips');
        both.append(toggle('Best', false, () => { best = k; fine.add(k); update(); }),
          toggle('Fine', false, () => { if (fine.has(k)) { fine.delete(k); if (best === k) best = null; } else fine.add(k); update(); }));
        box.append(both);
        row.append(box);
      }
      wrap.append(row, hint, go);
      update();
      return wrap;
    },
    range(part, trial, done) {
      const dimension = dimensions[part.id][trial.dimension];
      const { values, ordered } = dimension;
      const fine = new Set();
      let best = null;
      if (done) {
        if (ordered && done.from !== null) for (let k = values.indexOf(done.from); k <= values.indexOf(done.to); k += 1) fine.add(k);
        if (!ordered) for (const value of done.fine) fine.add(values.indexOf(value));
        best = done.best === null ? null : values.indexOf(done.best);
      }
      const wrap = el('div');
      wrap.append(el('h2', 'dimension', dimension.name));
      const list = el('div', 'values');
      const hint = el('p', 'hint');
      const go = next('Next', true, () => {
        const shown = (k) => (k === null ? null : values[k]);
        if (!ordered) answer({ fine: values.filter((_, k) => fine.has(k)), best: shown(best) });
        else {
          const run = runOf(fine, values.length);
          answer({ from: run ? values[run[0]] : null, to: run ? values[run[run.length - 1]] : null, best: shown(best) });
        }
      });
      const update = () => {
        for (const line of list.children) {
          const k = Number(line.dataset.value);
          const [f, b] = line.querySelectorAll('.flip');
          f.classList.toggle('on', fine.has(k));
          b.classList.toggle('on', best === k);
          f.setAttribute('aria-pressed', String(fine.has(k)));
          b.setAttribute('aria-pressed', String(best === k));
        }
        const run = ordered ? runOf(fine, values.length) : null;
        const broken = ordered && fine.size && !run;
        go.disabled = Boolean(broken);
        go.textContent = fine.size ? 'Next' : 'None is fine';
        hint.textContent = broken ? 'The fine values must be one run, with no gaps.'
          : (ordered ? 'Tick the values from the lowest to the highest that\'s fine; the best is optional.'
            : 'Tick every value that\'s fine; the best is optional.');
      };
      values.forEach((value, k) => {
        const line = el('div', 'value');
        line.dataset.value = String(k);
        line.append(el('span', 'text', value),
          toggle('Fine', false, () => { if (fine.has(k)) { fine.delete(k); if (best === k) best = null; } else fine.add(k); update(); }),
          toggle('Best', false, () => { if (best === k) best = null; else { best = k; fine.add(k); } update(); }));
        list.append(line);
      });
      wrap.append(list, hint, go);
      update();
      return wrap;
    },
    notes(part, trial, done) {
      const item = items[part.id][trial.item];
      const wrap = el('div', 'notes');
      wrap.append(media(item, item.label));
      const box = el('textarea', 'note');
      box.setAttribute('aria-label', 'What you notice');
      box.value = done ? done.note : '';
      wrap.append(box, next('Next', true, () => answer({ note: box.value.trim() })));
      return wrap;
    },
    redlines(part, trial, done) {
      return ticks(trial, done, 'Hard no', 'Your own hard nos, one a line');
    },
    checklist(part, trial, done) {
      return ticks(trial, done, part.mark, 'Anything else, one a line');
    },
  };

  // A list to tick, line by line, and a box for lines of his own.
  function ticks(trial, done, mark, ownText) {
    const checked = new Set(done ? done.checked : []);
    const wrap = el('div');
    const list = el('div', 'values');
    for (const line of trial.candidates) {
      const row = el('div', 'value');
      row.append(el('span', 'text', line), toggle(mark, checked.has(line), (node) => {
        if (checked.has(line)) checked.delete(line); else checked.add(line);
        node.classList.toggle('on', checked.has(line));
        node.setAttribute('aria-pressed', String(checked.has(line)));
      }));
      list.append(row);
    }
    const own = el('textarea', 'note');
    own.setAttribute('aria-label', ownText);
    own.placeholder = ownText;
    own.value = done ? done.own.join('\n') : '';
    wrap.append(list, own, next('Next', true, () => answer({
      checked: trial.candidates.filter((line) => checked.has(line)),
      own: own.value.split('\n').map((line) => line.trim()).filter(Boolean),
    })));
    return wrap;
  }

  function header() {
    const step = steps[state.at];
    const part = step.part;
    $('part').textContent = part ? part.title : design.title;
    $('count').textContent = step.kind === 'trial' ? 'Trial ' + (step.place + 1) + ' of ' + part.trials.length : '';
    const spent = part ? state.part_seconds[part.id] || 0 : 0;
    $('clock').textContent = part ? minutes(spent) + ' of ' + part.minutes + ' min' : '';
    $('clock').classList.toggle('over', Boolean(part) && spent > part.minutes * 60);
    $('back').disabled = state.at === 0;
  }

  function render() {
    shownAt = Date.now();
    header();
    screen.replaceChildren();
    window.scrollTo(0, 0);
    const step = steps[state.at];
    if (state.on_break) {
      screen.append(el('h1', '', 'A break'),
        el('p', 'lead', minutes(state.since_break) + ' minutes of judging since the last break. Look away from the screen for a few minutes; your answers are saved.'),
        button('Go on', 'next', () => {
          state.breaks.push({ at: new Date().toISOString(), after_seconds: state.since_break });
          state.since_break = 0;
          state.on_break = false;
          save();
          render();
        }));
    } else if (step.kind === 'welcome') {
      screen.append(el('h1', '', design.title));
      if (design.intro) screen.append(el('p', 'lead', design.intro));
      for (const line of [
        trialIds.length + ' trials in ' + design.parts.length + ' parts. Nothing is pre-selected and there are no right answers.',
        'Pick with the button under an option, or press its number. Videos start muted; unmute them with their controls. Tap an image to enlarge it.',
        'Every answer is saved on this device as you go: close the page and it opens where you left it. Parts takes you anywhere; Back goes one screen back.',
        'There\'s a break every ' + design.break_minutes + ' minutes of judging. At the end, press Save answers: it downloads one file.',
        'It works in Chrome on your computer or in your phone\'s browser. Your answers stay on the device where you started, so carry on there.',
      ]) screen.append(el('p', '', line));
      screen.append(button(Object.keys(state.answers).length ? 'Go on' : 'Start', 'next', () => go(state.at + 1)));
    } else if (step.kind === 'intro') {
      screen.append(el('h1', '', step.part.title));
      const list = el('dl', 'intro-lines');
      for (const { name, line } of step.part.intro) list.append(el('dt', '', name), el('dd', '', line));
      screen.append(list);
      const read = (skipped) => () => {
        state.intros[step.part.id] = { skipped, ms: Date.now() - shownAt };
        if (skipped) state.skip_intros = true;
        go(state.at + 1);
      };
      screen.append(button('Start', 'next', read(false)), button('Skip intros from now on', 'skip', read(true)));
    } else if (step.kind === 'trial') {
      const done = state.answers[step.trial.id];
      screen.append(el('h1', 'question', step.part.question), draw[step.part.type](step.part, step.trial, done));
      if (done) screen.append(button('Keep my answer', 'skip', () => go(state.at + 1)));
    } else {
      const left = trialIds.length - trialIds.filter((id) => id in state.answers).length;
      screen.append(el('h1', '', 'That\'s all'),
        el('p', 'lead', left ? left + ' trials have no answer yet: Parts shows where.' : 'Every trial has an answer. Thank you.'),
        el('p', '', 'Press Save answers below: it downloads answers-' + page + '-' + session + '.json. Tell the CEO it\'s there.'));
    }
  }

  function partsMenu() {
    const dialog = $('parts');
    const list = dialog.querySelector('.list');
    list.replaceChildren();
    for (const part of design.parts) {
      const ids = part.trials.map((trial) => trial.id);
      const answered = ids.filter((id) => id in state.answers).length;
      const first = steps.findIndex((step) => step.part === part);
      const open = steps.findIndex((step) => step.kind === 'trial' && step.part === part && !(step.trial.id in state.answers));
      const row = el('div', 'value');
      row.append(el('span', 'text', part.title + ': ' + answered + ' of ' + ids.length),
        button(answered === ids.length ? 'Redo' : (answered ? 'Go on' : 'Start'), 'flip', () => {
          dialog.close();
          go(open >= 0 && answered ? open : first);
        }));
      list.append(row);
    }
    dialog.showModal();
  }

  function exported() {
    return {
      format: 'taste-trial-answers-1', page, session, seed: design.seed, design_id: design.design_id, design,
      answers: state.answers, intros: state.intros, part_seconds: state.part_seconds, breaks: state.breaks,
      total_seconds: state.total_seconds, judging_seconds: state.judging_seconds, exported_at: new Date().toISOString(),
    };
  }
  window.trialAnswers = exported; // for the browser test

  function download() {
    const blob = new Blob([JSON.stringify(exported(), null, 1)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'answers-' + page + '-' + session + '.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 60000);
  }

  async function copy() {
    const text = JSON.stringify(exported(), null, 1);
    const out = $('out');
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (e) {
      out.value = text;
      out.classList.add('shown');
      out.select();
      try { copied = document.execCommand('copy'); } catch (e2) { copied = false; }
    }
    if (copied) out.classList.remove('shown');
    $('copy').textContent = copied ? 'Copied' : 'Copy the text above';
    setTimeout(() => { $('copy').textContent = 'Copy'; }, 3000);
  }

  $('save').addEventListener('click', download);
  $('copy').addEventListener('click', copy);
  $('back').addEventListener('click', () => {
    // From the break screen too: the break comes back on his next step forward, and is recorded only on Go on.
    state.on_break = false;
    go(state.at - 1);
  });
  $('menu').addEventListener('click', partsMenu);
  $('parts').querySelector('.close').addEventListener('click', () => $('parts').close());
  document.addEventListener('click', (event) => {
    const zoom = $('zoom');
    if (event.target.matches('img.zoomable')) {
      zoom.querySelector('img').src = event.target.src;
      zoom.showModal();
    } else if (event.target.closest('#zoom')) {
      zoom.close();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.target.matches('textarea, input') || event.metaKey || event.ctrlKey || event.altKey) return;
    const choose = screen.querySelector('button.pick[data-key="' + event.key + '"]');
    if (choose) choose.click();
  });

  // Time counts only while the page is in front and someone did something in the last two minutes.
  for (const type of ['pointerdown', 'keydown', 'input', 'scroll']) {
    document.addEventListener(type, () => { lastActive = Date.now(); }, { capture: true, passive: true });
  }
  setInterval(() => {
    if (document.visibilityState !== 'visible' || Date.now() - lastActive >= 120000) return;
    const step = steps[state.at];
    state.total_seconds += 5;
    if (step.part && !state.on_break) state.part_seconds[step.part.id] = (state.part_seconds[step.part.id] || 0) + 5;
    if (step.kind === 'trial' && !state.on_break) {
      state.judging_seconds += 5;
      state.since_break += 5;
    }
    header();
    save();
  }, 5000);

  restore();
  $('total').textContent = trialIds.length;
  save();
  render();
})();
