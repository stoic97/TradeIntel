/* Records what the design kit's scope-geometry.js returns for a fixed set of inputs.

   The Python port (services/production/api/scope_geometry.py) is held to these outputs
   byte for byte by tests/unit/api/test_scope_geometry.py (handoff section 8, T3). The
   repository has no Node toolchain, so the outputs are recorded once and committed;
   re-record only when the kit's geometry changes:

       node tests/fixtures/scope_geometry/record.js

   Inputs are synthetic: names are the Mirror's chapter and fact titles, figures are
   shaped like the Scope's (and a placeholder set like the kit's), never a trader's. */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const G = require(path.join(ROOT, 'docs/design/scope-kit/static/js/scope-geometry.js'));

const THREE = ['Where the money came from', 'Where your results came from', 'What we have not told you'];
const CHAPTERS = ['Where your results came from', 'Your patterns', 'Your behaviour', "What we couldn't read"];

function home(figures, states) {
  states = states || [];
  return {
    kind: 'home',
    items: CHAPTERS.map((name, i) => ({ name, figure: figures[i], href: `/mirror/chapter/${i + 1}?enter=in&amp;tap=${i + 1}`, state: states[i] || '' })),
    centre: { figure: figures[4], caption: 'of your result in five days' },
  };
}
function chapter(name, facts) {
  return {
    kind: 'chapter',
    items: facts.map((f, i) => Object.assign({ href: `/mirror/fact/${f.key}?enter=lens`, chart: f.chart || '', state: f.state || '', opened: !!f.opened }, { name: f.name, figure: f.figure })),
    centre: { name, scopeHref: '/mirror?enter=out&amp;tap=1' },
  };
}

const VIEWS = {
  home_phone_figures: [home(['96%', '30 · 10 min', '3', '38 of 40', '96%']), 'phone'],
  home_phone_placeholders: [home(['[N]%', '[N] · [N] min', '[N]', '[N] of [N]', '[N]%']), 'phone'],
  home_phone_long_figures: [home(['−₹12,34,567', '120 · 45 min', '1,234', '9,999 of 10,000', '100%']), 'phone'],
  home_phone_states: [home(['96%', '30 · 10 min', '—', '—', '96%'], ['', '', 'not-enough', 'not-in-file']), 'phone'],
  home_desktop: [home(['96%', '30 · 10 min', '3', '38 of 40', '96%']), 'desktop'],
  chapter_1_phone: [chapter('Where your results came from', [
    { key: 'worst-days', name: 'Your worst trading days', figure: '−₹24,000', chart: 'worst' },
    { key: 'share', name: 'Share of your result', figure: '96%', chart: 'share', opened: true },
    { key: 'money', name: 'Where the money came from', figure: '−₹9,000', chart: 'money' },
  ]), 'phone'],
  chapter_2_phone: [chapter('Your patterns', [
    { key: 'hold', name: 'How long you hold', figure: '30 · 10 min', chart: 'hold' },
    { key: 'strike', name: 'Strike rate', figure: '16%', chart: 'strike' },
    { key: 'run', name: 'Longest losing run', figure: '10 trades', chart: 'run' },
    { key: 'clock', name: 'The clock', figure: '10:00', chart: 'clock' },
  ]), 'phone'],
  chapter_3_phone: [chapter('Your behaviour', [
    { key: 'down', name: 'Trading on while already down', figure: '7 of 12', chart: 'down' },
    { key: 'busiest', name: 'Your busiest day', figure: '8 trades', chart: 'busy' },
  ]), 'phone'],
  chapter_4_phone: [chapter("What we couldn't read", [
    { key: 'unread', name: 'What we could not read', figure: '0 of 40', chart: 'read' },
    { key: 'risk', name: 'Trades with a risk figure', figure: '—', state: 'not-in-file' },
    { key: 'not-told', name: 'What we have not told you', figure: '4 things', chart: 'notold' },
  ]), 'phone'],
  chapter_2_not_enough: [chapter('Your patterns', [
    { key: 'hold', name: 'How long you hold', figure: '—', state: 'not-enough' },
    { key: 'strike', name: 'Strike rate', figure: '16%', chart: 'strike', opened: true },
    { key: 'run', name: 'Longest losing run', figure: '10 trades', chart: 'run', opened: true },
    { key: 'clock', name: 'The clock', figure: '10:00', chart: 'clock' },
  ]), 'phone'],
  chapter_1_desktop: [chapter('Where your results came from', [
    { key: 'worst-days', name: 'Your worst trading days', figure: '−₹24,000', chart: 'worst' },
    { key: 'share', name: 'Share of your result', figure: '96%', chart: 'share' },
    { key: 'money', name: 'Where the money came from', figure: '−₹9,000', chart: 'money' },
  ]), 'desktop'],
  chapter_five_facts: [chapter('Your risk', [
    { key: 'a', name: 'Trades with a risk figure', figure: '12 of 40', chart: 'risk' },
    { key: 'b', name: 'Your largest loss', figure: '−₹2,000' },
    { key: 'c', name: 'Size after a loss', figure: '1.5 lots' },
    { key: 'd', name: 'Trading on while already down', figure: '7 of 12' },
    { key: 'e', name: 'The clock', figure: '10:00' },
  ]), 'phone'],
  chapter_one_fact: [chapter('A chapter of one', [
    { key: 'only', name: 'Your worst trading days', figure: '−₹24,000', chart: 'worst' },
  ]), 'phone'],
};

const MINI = { worst: '<path d="M0 0"/>', share: '<path d="M1 1"/>' };

const cases = {
  _note: 'Recorded by record.js from docs/design/scope-kit/static/js/scope-geometry.js. Do not edit by hand.',
  fmt: [0, -0.004, 0.005, 1.005, 2.675, 179.999, -12.345, 49.425, 0.1 + 0.2, 1e-7, 129.565, -0.5, 1234.5678, 3.14159].map((n) => [n, G.fmt(n)]),
  sectors: [],
  ticks: [],
  name_labels: [],
  stacked_split: ['[N] of [N]', '10 trades', '[N] · [N] min', '96%', '—', '38 of 40'].map((f) => [f, G.stackedSplit(f)]),
  sans_width: ['Where your results came from', "What we couldn't read", 'mW Ii.,()', '₹12,34,567'].map((s) => [s, G.sansWidth(s, 11)]),
  dials: {},
  lenses: [],
  charts: [],
  trade_strips: [],
};

for (let n = 1; n <= 5; n++) for (const isHome of [true, false]) cases.sectors.push([n, isHome, G.sectors(n, isHome)]);

for (const [sizeName, n, isHome, rotation] of [['phone', 4, true, 0], ['phone', 3, false, 0], ['desktop', 5, false, 0], ['phone', 4, false, -45]]) {
  const size = G.SIZES[sizeName], rr = G.radii(size.R), sec = G.sectors(n, isHome);
  cases.ticks.push([sizeName, n, isHome, rotation, G.ticks(size.stageW / 2, size.stageH / 2, rr, sec.dividers, rotation)]);
}

const NAMES = CHAPTERS.concat(['Your worst trading days', 'Share of your result', 'Where the money came from', 'How long you hold', 'Strike rate', 'Longest losing run', 'The clock', 'Trading on while already down', 'Your busiest day', 'What we could not read', 'Trades with a risk figure', 'What we have not told you']);
for (const sizeName of ['phone', 'desktop']) {
  const size = G.SIZES[sizeName], rr = G.radii(size.R);
  for (const mid of [0, 36, 45, 60, 90, 120, 135, 180, 225, 240, 270, 300, 315, 324]) {
    for (const name of NAMES) cases.name_labels.push([sizeName, mid, name, G.nameLabel(name, mid, size.stageW / 2, size.stageH / 2, rr, size, { threeLineNames: THREE })]);
  }
}

for (const [key, [view, size]] of Object.entries(VIEWS)) {
  const d = G.buildDial(view, size, { threeLineNames: THREE });
  cases.dials[key] = {
    view, size,
    fig_size: d.figSize,
    stacked: d.slices.map((s) => !!s.contents.tail),
    radii_contents: d.slices.map((s) => [G.fmt(s.contents.x), G.fmt(s.contents.numberY)]),
    svg: G.renderDialSVG(d),
    svg_with_minis: key === 'chapter_1_phone' ? G.renderDialSVG(d, MINI) : null,  // one is enough to prove the slot
  };
}

for (let n = 1; n <= 5; n++) for (let i = 0; i < n; i++) cases.lenses.push([n, i, G.buildLens(n, i)]);

const DAILY = [-300, -8000, -200, -2000, -12000, -500, -1000, -1000];
const CHART_INPUTS = {
  worst: [[DAILY], [[500, -200, 0, 300, -50, -60, -70, 100, 0, -10]]],
  share: [[0.96], [1], [0.25]],
  money: [[[1500, 1000, 1000, 500, 500], [-2000, -2000, -2000, -2000, -2000]], [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]],
  hold: [[[30, 30, 30, 30, 20, 20], [30, 20, 15, 10, 10, 10, 60, 10, 10, 10, 10, 10, 10, 5, 5, 5, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10], 60], [[], [5], 10]],
  strike: [[6, 32, 2], [0, 0, 0], [10, 0, 0]],
  run: [[40, 16, 10], [3, 0, 1]],
  clock: [[[-5000, -13250, -1500, -1000], [3]], [[100, -100], []]],
  down: [[-1500, -600], [0, 0]],
  busy: [[[3, 6, 4, 5, 8, 4, 6, 4], 4.5], [[1], 1]],
  read: [[40, 40], [37, 40], [0, 0]],
  risk: [[20, 8, 8, 4], [0, 0, 0, 40]],
  notold: [[]],
};
const WITH_MINI = new Set(['share', 'hold', 'strike', 'run', 'down', 'read', 'risk', 'notold']);
for (const [kind, inputs] of Object.entries(CHART_INPUTS)) {
  for (const args of inputs) {
    for (const [w, h, mini] of [[350, 96, false], [36, 14, true]]) {
      const call = WITH_MINI.has(kind) ? args.concat([w, h, mini]) : args.concat([w, h]);
      const c = G.charts[kind](...call);
      cases.charts.push({ kind, args, w, h, mini, out: c, svg: G.renderChart(c, 'chart--page', true), inner: G.renderChart(c) });
    }
  }
}

for (const [times, width, height] of [[[0, 5, 30], 300, undefined], [[0], 120, 18], [[0, 0.5, 1, 1.5], 200, 24], [[3, 10], 90, undefined]]) {
  cases.trade_strips.push([times, width, height === undefined ? null : height, G.tradeStrip(times, width, height)]);
}

fs.mkdirSync(__dirname, { recursive: true });
fs.writeFileSync(path.join(__dirname, 'cases.json'), JSON.stringify(cases) + '\n');
console.log(`recorded ${Object.keys(cases.dials).length} dials, ${cases.lenses.length} lenses, ${cases.charts.length} charts, ${cases.name_labels.length} names`);
