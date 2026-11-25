// The page is plain HTML with native radio buttons; this adds saving, the counters, the zoom, the clock and the copy button.
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const KEY = 'taste-picker-' + root.dataset.page + '-round-' + root.dataset.round;
  const items = [...document.querySelectorAll('.item')];
  const aspects = [...document.querySelectorAll('.aspect')];
  const questions = [...document.querySelectorAll('.question')];
  const notes = [...document.querySelectorAll('.note')];
  const touched = new Set();
  const answered = new Set();
  const $ = (id) => document.getElementById(id);
  let place = 0;
  let saving = true;
  let seconds = 0;
  let lastActive = Date.now();

  const pick = (group) => group.querySelector('input:checked').value;
  const moved = (group) => pick(group) !== group.dataset.pre;
  const codeOf = (el) => el.closest('.item').dataset.code;
  const choose = (group, value) => {
    for (const input of group.querySelectorAll('input')) if (input.value === value) input.checked = true;
  };

  function counters() {
    let changed = 0;
    for (const aspect of aspects) {
      aspect.classList.toggle('changed', moved(aspect));
      if (moved(aspect)) changed += 1;
    }
    $('changed').textContent = changed;
  }

  function showSaving() {
    $('saved').textContent = saving ? 'Saved on this device as you go.' : 'This viewer can\'t save. Copy before you close it.';
  }

  function save() {
    const state = { choices: {}, notes: {}, answers: {}, touched: [...touched], answered: [...answered], place, seconds };
    for (const aspect of aspects) if (moved(aspect)) state.choices[codeOf(aspect) + '/' + aspect.dataset.aspect] = pick(aspect);
    for (const question of questions) if (moved(question)) state.answers[question.dataset.key] = pick(question);
    for (const note of notes) if (note.value.trim()) state.notes[codeOf(note)] = note.value;
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
      saving = true;
    } catch (e) {
      saving = false;
    }
    showSaving();
  }

  function restore() {
    let state = null;
    try {
      state = JSON.parse(localStorage.getItem(KEY));
    } catch (e) {
      saving = false;
    }
    if (!state) return;
    const choices = state.choices || {};
    const answers = state.answers || {};
    const written = state.notes || {};
    for (const aspect of aspects) choose(aspect, choices[codeOf(aspect) + '/' + aspect.dataset.aspect]);
    for (const question of questions) choose(question, answers[question.dataset.key]);
    for (const note of notes) note.value = written[codeOf(note)] || '';
    for (const code of state.touched || []) touched.add(code);
    for (const key of state.answered || []) answered.add(key);
    seconds = state.seconds || 0;
    place = state.place || 0;
    if (place && items[place]) items[place].scrollIntoView();
  }

  // Exposed so the page's copy can be checked without a click.
  window.pickerText = () => {
    const changed = [];
    const table = [];
    let choices = 0;
    let written = 0;
    for (const item of items) {
      const { code, account, kind } = item.dataset;
      const here = [...item.querySelectorAll('.aspect')];
      const name = (aspect) => aspect.getAttribute('aria-label');
      table.push(`${code} @${account} (${kind}): ${here.map((aspect) => `${name(aspect)} ${pick(aspect)}`).join(', ')}`);
      const mine = here.filter(moved).map((aspect) => `${name(aspect)} ${pick(aspect) === 'L' ? 'liked' : 'disliked'}`);
      const note = item.querySelector('.note').value.trim();
      choices += mine.length;
      if (note) written += 1;
      if (mine.length || note) changed.push(`${code} @${account}: ${mine.join(', ') || 'no change'}${note ? `. Note: ${note}` : ''}`);
    }
    const codes = (wanted) => items.map((item) => item.dataset.code).filter((code) => touched.has(code) === wanted).join(', ') || 'none';
    const answers = questions.map((question) => `${question.querySelector('legend').textContent}: ${pick(question)} (${moved(question) || answered.has(question.dataset.key) ? 'chosen' : 'pre-selected'})`);
    return [
      `Taste picks, ${root.dataset.page}, round ${root.dataset.round}. ${items.length} items, ${choices} choices changed, ${written} notes. Minutes on this page: ${Math.ceil(seconds / 60)}.`,
      '',
      'Page answers:',
      ...(answers.length ? answers : ['None asked.']),
      '',
      `Touched: ${codes(true)}`,
      `Left as pre-selected: ${codes(false)}`,
      '',
      'Changed or noted:',
      ...(changed.length ? changed : ['Nothing: every pre-selection stands.']),
      '',
      'All choices. L liked, D disliked.',
      ...table,
    ].join('\n');
  };

  async function copy() {
    const text = window.pickerText();
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
    setTimeout(() => { $('copy').textContent = 'Copy all choices'; }, 3000);
  }

  document.addEventListener('change', (event) => {
    if (event.target.matches('.toggle input')) counters();
    if (event.target.matches('.toggle input, .options input')) save();
  });
  document.addEventListener('input', (event) => {
    if (!event.target.matches('.note')) return;
    touched.add(codeOf(event.target));
    save();
  });
  document.addEventListener('click', (event) => {
    const zoom = $('zoom');
    if (event.target.matches('.toggle input')) {
      // On click, not change: tapping the choice already selected is still the Board's answer. It stays touched if changed back.
      touched.add(codeOf(event.target));
      save();
    } else if (event.target.matches('.options input')) {
      // The same for a page answer: tapped is chosen, even on its default.
      answered.add(event.target.closest('.question').dataset.key);
      save();
    } else if (event.target.matches('.frames img, .seen img')) {
      zoom.querySelector('img').src = event.target.src;
      zoom.showModal();
    } else if (event.target.closest('#zoom')) {
      zoom.close();
    }
  });
  $('copy').addEventListener('click', copy);

  // Minutes count only while the page is in front and someone did something in the last minute.
  for (const type of ['pointerdown', 'keydown', 'change', 'input', 'scroll']) {
    document.addEventListener(type, () => { lastActive = Date.now(); }, { capture: true, passive: true });
  }
  setInterval(() => {
    if (document.visibilityState !== 'visible' || Date.now() - lastActive >= 60000) return;
    seconds += 5;
    save();
  }, 5000);

  restore();
  counters();
  showSaving();
  $('total').textContent = items.length;
  $('place').textContent = place + 1;

  const watcher = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      place = items.indexOf(entry.target);
      $('place').textContent = place + 1;
      save();
    }
  }, { rootMargin: '-40% 0px -40% 0px' });
  items.forEach((item) => watcher.observe(item));
})();
