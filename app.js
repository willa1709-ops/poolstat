const grid = document.querySelector('#grid');
const summary = document.querySelector('#summary');
const updated = document.querySelector('#updated');
const reload = document.querySelector('#reload');

const preferredOrder = new Map([
  ['turnov-vysinka', 0],
  ['jablonec', 10],
  ['mb-stepanka', 20],
  ['mb-sokolovna', 30],
  ['jicin', 40],
  ['praha-hloubetin', 50],
]);

function sortedPools(pools) {
  return [...pools].sort((a, b) => {
    const aReconstruction = a.status === 'reconstruction';
    const bReconstruction = b.status === 'reconstruction';
    if (aReconstruction !== bReconstruction) return aReconstruction ? 1 : -1;

    const aOrder = preferredOrder.get(a.id) ?? 500;
    const bOrder = preferredOrder.get(b.id) ?? 500;
    if (aOrder !== bOrder) return aOrder - bOrder;

    return String(a.name || '').localeCompare(String(b.name || ''), 'cs');
  });
}

function stateFor(p) {
  if (p.status === 'reconstruction') return ['rekonstrukce', 'reconstruction'];
  if (p.open_now) return ['otevřeno pro veřejnost', 'open'];
  return ['teď zavřeno', 'closed'];
}

function laneLength(p) {
  const values = Array.isArray(p.lane_lengths_m) ? p.lane_lengths_m : [];
  if (!values.length) return '—';
  return values.map(v => `${String(v).replace('.', ',')} m`).join(' + ');
}

function lanes(p) {
  if (p.status === 'reconstruction') return '0';
  if (p.free_lanes_now === null || p.free_lanes_now === undefined) return '?';
  return String(p.free_lanes_now);
}

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

function safeExternalUrl(raw) {
  if (!raw) return null;
  try {
    const u = new URL(raw);
    return u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

function externalLink(label, rawUrl) {
  const href = safeExternalUrl(rawUrl);
  if (!href) return null;
  const a = node('a', '', label);
  a.href = href;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  return a;
}

function stat(label, value, options = {}) {
  const classes = ['stat'];
  if (options.primary) classes.push('stat-primary');
  const box = node('div', classes.join(' '));
  box.append(node('span', 'label', label));
  box.append(node('span', `value${options.unknown ? ' unknown' : ''}`, value));
  return box;
}

function detailsNote(text) {
  const details = node('details', 'details');
  details.append(node('summary', '', 'Podrobnosti'));
  details.append(node('p', 'note', text));
  return details;
}

function card(p) {
  const [label, cls] = stateFor(p);
  const article = node('article', 'card');

  const top = node('div', 'top');
  const heading = node('div');
  heading.append(node('div', 'city', p.city || ''));
  heading.append(node('h2', '', p.name || 'Neznámý bazén'));
  top.append(heading);
  top.append(node('span', `state ${cls}`, label));
  article.append(top);

  const opening = p.status === 'reconstruction'
    ? `plán ${p.expected_opening || 'neuveden'}`
    : (p.public_hours_today || '—');
  const free = lanes(p);
  const laneLabel = p.total_lanes ? `${free} / ${p.total_lanes}` : free;

  const stats = node('div', 'stats');
  stats.append(stat('Dnes veřejnost', opening, { primary: true }));
  stats.append(stat('Volné dráhy teď', laneLabel, { unknown: free === '?' }));
  stats.append(stat('Délka dráhy', laneLength(p)));
  stats.append(stat('Drah celkem', p.total_lanes ?? '—'));
  article.append(stats);

  if (p.warning) article.append(node('div', 'warning', p.warning));
  if (p.source_fetch_ok === false) {
    article.append(node('div', 'warning', 'Noční kontrola oficiálního zdroje se nezdařila; zobrazen je uložený pravidelný rozvrh.'));
  }
  if (p.notes) article.append(detailsNote(p.notes));

  const links = node('div', 'links');
  const source = externalLink('Oficiální zdroj ↗', p.source_url);
  const laneSource = externalLink('Rozpis drah ↗', p.lane_source_url);
  if (source) links.append(source);
  if (laneSource) links.append(laneSource);
  if (links.childElementCount) article.append(links);

  return article;
}

function pill(text) {
  return node('span', 'pill', text);
}

function staleHours(generatedAt) {
  const d = new Date(generatedAt);
  if (Number.isNaN(d.getTime())) return null;
  return (Date.now() - d.getTime()) / 3600000;
}

async function load() {
  grid.setAttribute('aria-busy', 'true');
  reload.disabled = true;
  reload.textContent = 'Načítám…';
  grid.replaceChildren(node('article', 'card', 'Načítám…'));

  try {
    const r = await fetch(`data/pools.json?ts=${Date.now()}`, {
      cache: 'no-store',
      credentials: 'omit',
      referrerPolicy: 'no-referrer'
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    if (!data || !Array.isArray(data.pools)) throw new Error('Neplatný formát dat');

    const pools = sortedPools(data.pools);
    grid.replaceChildren(...pools.map(card));

    const open = pools.filter(p => p.open_now).length;
    const reconstruction = pools.filter(p => p.status === 'reconstruction').length;
    summary.replaceChildren(
      pill(`${open} právě otevřeno`),
      pill(`${pools.length} sledovaných míst`),
      pill(`${reconstruction} v rekonstrukci`)
    );

    const age = staleHours(data.generated_at);
    if (age !== null && age > 30) {
      summary.append(pill(`pozor: data jsou ${Math.floor(age)} h stará`));
    }

    const d = new Date(data.generated_at);
    updated.textContent = Number.isNaN(d.getTime())
      ? 'Čas aktualizace není známý'
      : `Data z noční kontroly: ${d.toLocaleString('cs-CZ')}`;
  } catch (e) {
    const errorCard = node('article', 'card');
    errorCard.append(node('b', '', 'Data se nepodařilo načíst.'));
    errorCard.append(node('p', 'note', e instanceof Error ? e.message : 'Neznámá chyba'));
    grid.replaceChildren(errorCard);
  } finally {
    grid.setAttribute('aria-busy', 'false');
    reload.disabled = false;
    reload.textContent = 'Načíst znovu';
  }
}

reload.addEventListener('click', load);
load();
