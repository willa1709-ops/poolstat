const grid = document.querySelector('#grid');
const summary = document.querySelector('#summary');
const updated = document.querySelector('#updated');
const reload = document.querySelector('#reload');

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

function stat(label, value, unknown = false) {
  const box = node('div', 'stat');
  box.append(node('span', 'label', label));
  const val = node('span', `value${unknown ? ' unknown' : ''}`, value);
  box.append(val);
  return box;
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
  stats.append(stat('Dnes veřejnost', opening));
  stats.append(stat('Volné dráhy teď', laneLabel, free === '?'));
  stats.append(stat('Drah celkem', p.total_lanes ?? '—'));
  stats.append(stat('Délka dráhy', laneLength(p)));
  article.append(stats);

  if (p.warning) article.append(node('div', 'warning', p.warning));
  if (p.source_fetch_ok === false) {
    article.append(node('div', 'warning', 'Noční kontrola oficiálního zdroje se nezdařila; zobrazen je uložený pravidelný rozvrh.'));
  }
  if (p.notes) article.append(node('p', 'note', p.notes));

  const links = node('div', 'links');
  const source = externalLink('Oficiální zdroj ↗', p.source_url);
  const laneSource = externalLink('Rozpis drah ↗', p.lane_source_url);
  if (source) links.append(source);
  if (laneSource) links.append(laneSource);
  article.append(links);

  return article;
}

function pill(htmlFreeText) {
  return node('span', 'pill', htmlFreeText);
}

function staleHours(generatedAt) {
  const d = new Date(generatedAt);
  if (Number.isNaN(d.getTime())) return null;
  return (Date.now() - d.getTime()) / 3600000;
}

async function load() {
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

    grid.replaceChildren(...data.pools.map(card));

    const open = data.pools.filter(p => p.open_now).length;
    const reconstruction = data.pools.filter(p => p.status === 'reconstruction').length;
    summary.replaceChildren(
      pill(`${open} právě otevřeno`),
      pill(`${data.pools.length} sledovaných míst`),
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
  }
}

reload.addEventListener('click', load);
load();
