const grid = document.querySelector('#grid');
const summary = document.querySelector('#summary');
const updated = document.querySelector('#updated');
const reload = document.querySelector('#reload');
const pageTitle = document.querySelector('#page-title');
const tabToday = document.querySelector('#tab-today');
const tabTomorrow = document.querySelector('#tab-tomorrow');
let currentData = null;
let currentView = 'today';

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


function pragueNow(timeZone = 'Europe/Prague') {
  const now = new Date();
  try {
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23'
    });
    const parts = Object.fromEntries(
      fmt.formatToParts(now)
        .filter(p => p.type !== 'literal')
        .map(p => [p.type, p.value])
    );
    const weekdayMap = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
    return {
      date: `${parts.year}-${parts.month}-${parts.day}`,
      weekday: weekdayMap[parts.weekday],
      minutes: Number(parts.hour) * 60 + Number(parts.minute)
    };
  } catch {
    const jsDay = now.getDay();
    return {
      date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`,
      weekday: jsDay === 0 ? 6 : jsDay - 1,
      minutes: now.getHours() * 60 + now.getMinutes()
    };
  }
}

function hhmmToMinutes(value) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(value || '').trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return h * 60 + min;
}

function parseHoursText(text) {
  const re = /(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})/g;
  const out = [];
  let match;
  while ((match = re.exec(String(text || ''))) !== null) out.push([match[1], match[2]]);
  return out;
}

function formatIntervals(intervals) {
  if (!intervals || !intervals.length) return '—';
  return intervals.map(([a, b]) => `${a}–${b}`).join(', ');
}

function shiftedClock(clock, days) {
  const parts = String(clock.date || '').split('-').map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) {
    return { date: clock.date, weekday: (clock.weekday + days + 7) % 7, minutes: clock.minutes };
  }
  const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + days));
  return {
    date: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`,
    weekday: (clock.weekday + days + 7) % 7,
    minutes: clock.minutes
  };
}

function scheduleForDay(p, clock, useTodayExceptions) {
  if (p.status === 'reconstruction') return [];

  if (useTodayExceptions && p.date === clock.date && p.public_hours_today) {
    const detected = parseHoursText(p.public_hours_today);
    if (detected.length || p.public_hours_today === '—') return detected;
  }

  if (p.weekly_hours && clock.weekday !== undefined) {
    const weekly = p.weekly_hours[String(clock.weekday)];
    if (Array.isArray(weekly)) return weekly;
  }

  if (useTodayExceptions && p.date === clock.date) return parseHoursText(p.public_hours_today);
  return [];
}

function scheduleForToday(p, clock) {
  return scheduleForDay(p, clock, true);
}

function scheduleForTomorrow(p, clock) {
  return scheduleForDay(p, shiftedClock(clock, 1), false);
}

function liveState(p, clock) {
  if (p.status === 'reconstruction') return { open: false, intervals: [] };
  const intervals = scheduleForToday(p, clock);

  for (const interval of intervals) {
    const start = hhmmToMinutes(interval[0]);
    const end = hhmmToMinutes(interval[1]);
    if (start === null || end === null) continue;
    if (clock.minutes >= start && clock.minutes < end) {
      return { open: true, intervals };
    }
  }
  return { open: false, intervals };
}

function stateFor(p, live) {
  if (p.status === 'reconstruction') return ['rekonstrukce', 'reconstruction'];
  if (live.open) return ['otevřeno pro veřejnost', 'open'];
  return ['teď zavřeno', 'closed'];
}

function futureStateFor(p, intervals) {
  if (p.status === 'reconstruction') return ['rekonstrukce', 'reconstruction'];
  if (intervals.length) return ['veřejnost zítra', 'future'];
  return ['zítra bez veřejnosti', 'closed'];
}

function laneLength(p) {
  const values = Array.isArray(p.lane_lengths_m) ? p.lane_lengths_m : [];
  if (!values.length) return '—';
  return values.map(v => `${String(v).replace('.', ',')} m`).join(' + ');
}

function liveFreeLanes(p, clock) {
  const days = p.lane_availability && p.lane_availability.days;
  const ranges = days && days[clock.date];
  if (!Array.isArray(ranges)) return null;

  for (const item of ranges) {
    const start = hhmmToMinutes(item.from);
    const end = item.to === '24:00' ? 1440 : hhmmToMinutes(item.to);
    if (start === null || end === null) continue;
    if (clock.minutes >= start && clock.minutes < end) {
      return Number.isInteger(item.free) ? item.free : null;
    }
  }
  return null;
}

function lanes(p, live, clock) {
  if (p.status === 'reconstruction' || !live.open) return '0';
  if (Number.isInteger(p.free_lanes_when_open)) return String(p.free_lanes_when_open);
  const current = liveFreeLanes(p, clock);
  return current === null ? '?' : String(current);
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

function card(p, clock, view) {
  const isTomorrow = view === 'tomorrow';
  const live = liveState(p, clock);
  const tomorrowIntervals = isTomorrow ? scheduleForTomorrow(p, clock) : null;
  const [label, cls] = isTomorrow ? futureStateFor(p, tomorrowIntervals) : stateFor(p, live);
  const article = node('article', 'card');

  const top = node('div', 'top');
  const heading = node('div');
  heading.append(node('div', 'city', p.city || ''));
  heading.append(node('h2', '', p.name || 'Neznámý bazén'));
  top.append(heading);
  top.append(node('span', `state ${cls}`, label));
  article.append(top);

  const intervals = isTomorrow ? tomorrowIntervals : live.intervals;
  const opening = p.status === 'reconstruction'
    ? `plán ${p.expected_opening || 'neuveden'}`
    : formatIntervals(intervals);

  const stats = node('div', 'stats');
  stats.append(stat(isTomorrow ? 'Zítra veřejnost' : 'Dnes veřejnost', opening, { primary: true }));

  if (!isTomorrow) {
    const free = lanes(p, live, clock);
    const laneLabel = p.total_lanes ? `${free} / ${p.total_lanes}` : free;
    stats.append(stat('Volné dráhy teď', laneLabel, { unknown: free === '?' }));
  }

  stats.append(stat('Délka dráhy', laneLength(p)));
  article.append(stats);

  if (!isTomorrow && p.warning && p.date === clock.date) article.append(node('div', 'warning', p.warning));
  if (p.source_fetch_ok === false) {
    article.append(node('div', 'warning', 'Noční kontrola oficiálního zdroje se nezdařila; zobrazen je uložený pravidelný rozvrh.'));
  }
  if (p.notes) article.append(detailsNote(p.notes));

  const links = node('div', 'links');
  const infoUrl = p.updates_url || p.source_url;
  const infoLabel = p.updates_url ? (p.updates_label || 'Aktuality') : 'Oficiální zdroj';
  const source = externalLink(`${infoLabel} ↗`, infoUrl);
  const laneSource = externalLink(`${p.lane_source_label || 'Rozpis drah'} ↗`, p.lane_source_url);
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

function setActiveTab(view) {
  const tomorrow = view === 'tomorrow';
  tabToday.classList.toggle('active', !tomorrow);
  tabTomorrow.classList.toggle('active', tomorrow);
  tabToday.setAttribute('aria-selected', String(!tomorrow));
  tabTomorrow.setAttribute('aria-selected', String(tomorrow));
  pageTitle.textContent = tomorrow ? 'Kde si zítra zaplavat?' : 'Kde si dnes zaplavat?';
}

function renderData(data) {
  if (!data || !Array.isArray(data.pools)) throw new Error('Neplatný formát dat');
  currentData = data;

  const clock = pragueNow(data.timezone || 'Europe/Prague');
  const pools = sortedPools(data.pools);
  const isTomorrow = currentView === 'tomorrow';
  setActiveTab(currentView);
  grid.replaceChildren(...pools.map(p => card(p, clock, currentView)));

  const reconstruction = pools.filter(p => p.status === 'reconstruction').length;

  if (isTomorrow) {
    const withPublic = pools.filter(p => p.status !== 'reconstruction' && scheduleForTomorrow(p, clock).length > 0).length;
    summary.replaceChildren(
      pill(`${withPublic} se zítřejším časem pro veřejnost`),
      pill(`${pools.length} sledovaných míst`),
      pill(`${reconstruction} v rekonstrukci`)
    );
  } else {
    const open = pools.filter(p => liveState(p, clock).open).length;
    summary.replaceChildren(
      pill(`${open} právě otevřeno`),
      pill(`${pools.length} sledovaných míst`),
      pill(`${reconstruction} v rekonstrukci`)
    );
  }

  const age = staleHours(data.generated_at);
  if (age !== null && age > 30) {
    summary.append(pill(`pozor: data jsou ${Math.floor(age)} h stará`));
  }

  const d = new Date(data.generated_at);
  updated.textContent = Number.isNaN(d.getTime())
    ? 'Čas aktualizace není známý'
    : isTomorrow
      ? `Rozvrhy z noční kontroly: ${d.toLocaleString('cs-CZ')} · zítřek podle týdenního rozvrhu`
      : `Rozvrhy z noční kontroly: ${d.toLocaleString('cs-CZ')} · stav otevřeno/zavřeno počítán právě teď`;
}

async function load() {
  grid.setAttribute('aria-busy', 'true');
  reload.disabled = true;
  reload.textContent = 'Načítám…';
  grid.replaceChildren(node('article', 'card', 'Načítám…'));

  try {
    const dataUrl = new URL('./data/pools.json', document.baseURI);
    dataUrl.searchParams.set('ts', String(Date.now()));
    const r = await fetch(dataUrl, {
      cache: 'no-store',
      credentials: 'omit',
      referrerPolicy: 'no-referrer'
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    renderData(data);
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

tabToday.addEventListener('click', () => {
  currentView = 'today';
  if (currentData) renderData(currentData);
});

tabTomorrow.addEventListener('click', () => {
  currentView = 'tomorrow';
  if (currentData) renderData(currentData);
});

reload.addEventListener('click', load);
load();

window.setInterval(() => {
  if (currentData) renderData(currentData);
}, 60000);
