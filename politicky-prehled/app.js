'use strict';
let data = JSON.parse(document.getElementById('initial-data').textContent);
const sourceConfig = JSON.parse(document.getElementById('source-config').textContent);
const allowedSourceHosts = new Set(sourceConfig.flatMap(s => s.hosts));
let category = 'all';
let latestData = data, viewingArchive = false, selectionRequest = 0;
let archiveEntries = [];
const $ = selector => document.querySelector(selector);
const buttons = [...document.querySelectorAll('[data-filter]')];
const dateFormat = new Intl.DateTimeFormat('cs-CZ', {timeZone:'Europe/Prague', dateStyle:'long'});
const timeFormat = new Intl.DateTimeFormat('cs-CZ', {timeZone:'Europe/Prague', timeStyle:'short'});
const fullFormat = new Intl.DateTimeFormat('cs-CZ', {timeZone:'Europe/Prague', dateStyle:'short', timeStyle:'short'});
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function render() {
  const now = Date.now();
  const articles = viewingArchive ? data.articles : data.articles.filter(a => {
    const published = Date.parse(a.published_at);
    return Number.isFinite(published) && published <= now && published >= now - 86400000;
  });
  const openUrls = new Set([...document.querySelectorAll('#news details[open]')].map(el => el.closest('article').dataset.url));
  const focused = document.activeElement;
  const focusedUrl = focused?.closest('#news article')?.dataset.url;
  const fragment = document.createDocumentFragment();
  for (const a of articles) {
    const url = new URL(a.url);
    if (url.protocol !== 'https:' || !allowedSourceHosts.has(url.hostname)) continue;
    const card = element('article');
    card.dataset.category = a.category;
    card.dataset.url = a.url;
    const meta = element('div', '', 'meta');
    const time = element('time', fullFormat.format(new Date(a.published_at)));
    time.dateTime = a.published_at;
    meta.append(element('span', a.category === 'domaci' ? 'Domácí politika' : 'Zahraniční politika', 'category'), time);
    const source = element('div', '', 'source');
    const link = element('a', 'Číst původní článek ↗');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    source.append(element('span', (a.source === 'ČTK / České noviny' ? 'Zdroj · ' : 'Výňatek z anotace · ') + a.source), link);
    const heading = element('h2');
    const titleLink = element('a', a.title);
    titleLink.href = url.href;
    heading.append(titleLink);
    card.append(meta, heading, element('p',a.summary));
    if (a.importance) {
      const analysis = a.importance_kind === 'analysis';
      const why = element(analysis ? 'details' : 'div', '', analysis ? 'why impact' : 'why');
      const note = element('small', a.importance_kind === 'possible_impact' ? 'Možný dopad · odhad' : 'Tematický kontext', 'small');
      note.style.display = 'block'; note.style.marginTop = '6px';
      const label = element('b', 'Proč je to důležité');
      if (analysis) {
        const summary = element('summary');
        summary.append(label, element('span', a.importance.split('\n\n')[0], 'excerpt'),
          element('span', 'Celý rozbor', 'action expand'), element('span', 'Sbalit rozbor', 'action collapse'));
        why.append(summary);
        why.open = openUrls.has(a.url);
        for (const paragraph of a.importance.split('\n\n')) why.append(element('p', paragraph));
        note.textContent = 'Rozbor dopadů';
        const evidence = a.analysis_url && new URL(a.analysis_url);
        if (evidence && evidence.protocol === 'https:' && allowedSourceHosts.has(evidence.hostname)) {
          const citation = element('a', 'Podklad: ' + a.analysis_source);
          citation.href = evidence.href;
          note.append(' · ', citation);
        }
      } else {
        why.append(label);
        if (a.importance_kind === 'pending') note.textContent = 'Stav rozboru';
        why.append(document.createTextNode(a.importance));
      }
      why.append(note);
      card.append(why);
    }
    card.append(source);
    fragment.append(card);
  }
  $('#news').replaceChildren(fragment);
  if (focusedUrl && focused.tagName === 'SUMMARY') {
    [...document.querySelectorAll('#news article')].find(card => card.dataset.url === focusedUrl)
      ?.querySelector('summary')?.focus({preventScroll:true});
  }
  const updated = new Date(data.updated_at);
  $('#editionDate').textContent = dateFormat.format(updated);
  $('#editionTime').textContent = timeFormat.format(updated) + ' · Praha';
  const stale = now - updated.getTime() > 2 * 3600000;
  const status = $('#updateStatus');
  status.classList.toggle('warning', stale || Boolean(data.unavailable_sources?.length));
  status.textContent = stale ? 'Aktualizace se opozdila. Zobrazen je čas poslední úspěšné kontroly; články starší než 24 hodin se nezobrazují.' :
    'Automatická kontrola každou hodinu · Články zveřejněné za posledních 24 hodin · Časy v pásmu Praha.';
  $('#editionLabel').textContent = viewingArchive ? 'Archivní vydání' : 'Poslední úspěšná aktualizace';
  $('#sectionLabel').textContent = viewingArchive ? 'Archiv přehledu' : 'Aktuální přehled';
  $('#editionNote').textContent = viewingArchive ? 'Obsah uložený v uvedený čas.' : 'Starší vydání najdete v archivu.';
  if (viewingArchive) {
    status.classList.remove('warning');
    status.textContent = 'Archivní vydání z ' + fullFormat.format(updated) + ' · Zobrazen je tehdejší výběr článků. Pro dnešní zprávy zvolte aktuální vydání.';
  }
  if (data.unavailable_sources?.length) status.textContent += ' Při poslední kontrole nebyl dostupný zdroj: ' + data.unavailable_sources.join(', ') + '.';
  status.hidden = viewingArchive || (!stale && !data.unavailable_sources?.length);
  renderSources();
  filter();
}
function renderSources() {
  const list = $('#sourceList'), fragment = document.createDocumentFragment();
  for (const source of sourceConfig) {
    const row = element('li'), link = element('a', source.name);
    link.href = source.site; link.target = '_blank'; link.rel = 'noopener noreferrer';
    const state = data.sources?.find(s => s.name === source.name);
    const count = data.articles.filter(a => a.source === source.name).length;
    let note = state ? (state.status === 'ok' ? 'Zkontrolováno' : state.status === 'partial' ? 'Částečně dostupný' : 'Při kontrole nedostupný') : 'Bez záznamu kontroly v tomto vydání';
    if (state?.status === 'ok' && state.candidates > 0 && state.free_articles_checked === 0) note += ' · volný článek nepotvrzen';
    note += ' · ve vydání: ' + count;
    row.append(link, element('span', note, 'small')); fragment.append(row);
  }
  list.replaceChildren(fragment);
}
function filter() {
  const query = $('#search').value.trim().toLocaleLowerCase('cs');
  let count = 0;
  document.querySelectorAll('#news article').forEach(card => {
    card.hidden = (category !== 'all' && card.dataset.category !== category) || !card.textContent.toLocaleLowerCase('cs').includes(query);
    if (!card.hidden) count++;
  });
  $('#count').textContent = count + ' ' + (count === 1 ? 'zpráva' : count >= 2 && count <= 4 ? 'zprávy' : 'zpráv');
  $('#empty').hidden = count !== 0;
  $('#empty').textContent = data.articles.length ? 'Tomuto filtru neodpovídá žádná zpráva ve vybraném vydání.' : 'Za posledních 24 hodin nebyly nalezeny články odpovídající výběru.';
}
buttons.forEach(button => button.addEventListener('click', () => {
  category = button.dataset.filter;
  buttons.forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  filter();
}));
$('#search').addEventListener('input', filter);
let refreshing = false;
async function refresh() {
  if (refreshing || document.hidden) return;
  refreshing = true;
  try {
    const response = await fetch('data.json', {cache:'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const next = await response.json();
    if (!Array.isArray(next.articles) || !Number.isFinite(Date.parse(next.updated_at))) throw new Error('Invalid edition');
    if (Date.parse(next.updated_at) < Date.parse(latestData.updated_at)) return;
    const changed = JSON.stringify(next) !== JSON.stringify(latestData);
    latestData = next;
    if (!viewingArchive && changed) { data = next; render(); }
  } catch (error) {
    // Preserve the real successful update time and keep expiry checks running.
    console.warn('Aktuální vydání se nepodařilo načíst.', error);
  } finally {
    refreshing = false;
  }
}
async function loadArchive() {
  try {
    const response = await fetch('archive/index.json', {cache:'no-store'});
    if (!response.ok) throw new Error('Archive unavailable');
    const entries = await response.json();
    if (!Array.isArray(entries)) throw new Error('Invalid archive');
    archiveEntries = entries.filter(e => /^archive\/\d{4}-\d{2}-\d{2}\/[\d-]+\.json$/.test(e.path) && Number.isFinite(Date.parse(e.updated_at)));
    const select = $('#edition'), selected = select.value;
    const options = [element('option', 'Aktuální vydání')]; options[0].value = 'current';
    for (const entry of archiveEntries) {
      const option = element('option', fullFormat.format(new Date(entry.updated_at)) + ' · ' + entry.count + ' zpráv');
      option.value = entry.path; options.push(option);
    }
    select.replaceChildren(...options);
    select.value = options.some(o => o.value === selected) ? selected : 'current';
    $('#archiveMessage').textContent = archiveEntries.length ? 'Dostupná vydání od ' + fullFormat.format(new Date(archiveEntries[archiveEntries.length-1].updated_at)) + '.' : 'Archiv se naplní po první aktualizaci.';
  } catch (error) {
    $('#archiveMessage').textContent = 'Seznam archivu se nepodařilo načíst. Aktuální přehled je dostupný.';
  }
}
$('#edition').addEventListener('change', async event => {
  const value = event.target.value, request = ++selectionRequest;
  if (value === 'current') { viewingArchive = false; data = latestData; render(); return; }
  const entry = archiveEntries.find(e => e.path === value);
  if (!entry) return;
  try {
    $('#archiveMessage').textContent = 'Načítání vydání…';
    const response = await fetch(entry.path, {cache:'no-store'});
    if (!response.ok) throw new Error('Edition unavailable');
    const edition = await response.json();
    if (!Array.isArray(edition.articles) || edition.updated_at !== entry.updated_at) throw new Error('Invalid edition');
    if (request !== selectionRequest) return;
    viewingArchive = true; data = edition; render();
    $('#archiveMessage').textContent = 'Zobrazeno uložené vydání z ' + fullFormat.format(new Date(edition.updated_at)) + '.';
  } catch (error) {
    if (request !== selectionRequest) return;
    $('#edition').value = viewingArchive ? archiveEntries.find(e => e.updated_at === data.updated_at)?.path || 'current' : 'current';
    $('#archiveMessage').textContent = 'Vydání se nepodařilo načíst. Zůstává předchozí přehled.';
  }
});
$('#news').addEventListener('click', event => {
  const panel = event.target.closest('details.impact[open]');
  if (!panel || event.target.closest('summary, a') || !window.getSelection().isCollapsed) return;
  panel.open = false;
  panel.querySelector('summary').focus({preventScroll: true});
});

render(); refresh(); loadArchive();
setInterval(loadArchive, 5 * 60000);
setInterval(refresh, 30000);
setInterval(render, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

document.querySelectorAll('.utility-row details').forEach(panel=>panel.addEventListener('toggle',()=>{if(panel.open)document.querySelectorAll('.utility-row details').forEach(other=>{if(other!==panel)other.open=false;});}));
