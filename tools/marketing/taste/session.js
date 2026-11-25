// The session picker is plain HTML with native radio buttons; this adds saving, the counter, the zoom, the clock and
// the copy button, as picker.js does for the taste picker.
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const { page, session } = root.dataset;
  const KEY = 'taste-session-' + page + '-' + session;
  const items = [...document.querySelectorAll('.item')];
  const touched = new Set();
  const $ = (id) => document.getElementById(id);
  let place = 0;
  let saving = true;
  let seconds = 0;
  let lastActive = Date.now();

  const idOf = (el) => el.closest('.item').dataset.id;
  const pre = (item) => item.querySelector('.choice').dataset.pre;
  const pick = (item) => item.querySelector('.choice input:checked').value;
  const moved = (item) => pick(item) !== pre(item);
  const noteOf = (item) => item.querySelector('.note');

  function counters() {
    for (const item of items) item.classList.toggle('changed', moved(item));
    $('changed').textContent = items.filter(moved).length;
  }

  function showSaving() {
    $('saved').textContent = saving ? 'Saved on this device as you go.' : 'This viewer can\'t save. Copy before you close it.';
  }

  function save() {
    const state = { choices: {}, notes: {}, touched: [...touched], place, seconds };
    for (const item of items) {
      if (moved(item)) state.choices[item.dataset.id] = pick(item);
      if (noteOf(item).value.trim()) state.notes[item.dataset.id] = noteOf(item).value;
    }
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
    const written = state.notes || {};
    for (const item of items) {
      for (const input of item.querySelectorAll('.choice input')) if (input.value === choices[item.dataset.id]) input.checked = true;
      noteOf(item).value = written[item.dataset.id] || '';
    }
    for (const id of state.touched || []) touched.add(id);
    seconds = state.seconds || 0;
    place = state.place || 0;
    if (place && items[place]) items[place].scrollIntoView();
  }

  // Exposed so the page's copy can be checked without a click.
  window.pickerText = () => {
    const lines = items.map((item) => {
      const { id } = item.dataset;
      const note = noteOf(item).value.trim();
      const how = moved(item) ? `changed from ${pre(item)}` : 'the default';
      return `${id}: ${pick(item)} (${how}, ${touched.has(id) ? 'touched' : 'untouched'})${note ? `. Note: ${note}` : ''}`;
    });
    const written = items.filter((item) => noteOf(item).value.trim()).length;
    return [
      `Session answers, ${page}, ${session}. ${items.length} items, ${items.filter(moved).length} changed, ${written} notes. Minutes on this page: ${Math.ceil(seconds / 60)}.`,
      '',
      ...lines,
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
    setTimeout(() => { $('copy').textContent = 'Copy all answers'; }, 3000);
  }

  document.addEventListener('change', (event) => {
    if (!event.target.matches('.choice input')) return;
    counters();
    save();
  });
  document.addEventListener('input', (event) => {
    if (!event.target.matches('.note')) return;
    touched.add(idOf(event.target));
    save();
  });
  document.addEventListener('click', (event) => {
    const zoom = $('zoom');
    if (event.target.matches('.choice input')) {
      // On click, not change: tapping the answer already selected is still the Board's answer.
      touched.add(idOf(event.target));
      save();
    } else if (event.target.matches('.figs img')) {
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
