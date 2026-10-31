/* =====================================================================
   PlusEV Scope — scope-geometry.js
   ---------------------------------------------------------------------
   Pure functions that place everything on the Scope dial and in the
   charts. No DOM, no randomness, no globals: the same inputs always
   give the same output, so this file can be ported line by line to a
   Python module behind a Jinja macro.

   PORTING NOTES (Python):
   * Every function here is pure and returns plain data (numbers,
     strings, arrays, objects) — map to floats, str, list, dict.
   * Angles are degrees, clockwise from twelve o'clock.
     polar(cx, cy, r, a) = (cx + r·sin a, cy − r·cos a).
   * Path strings are built with fmt() (2-decimal rounding) so Python
     and JS produce byte-identical SVG. Use round(n, 2) and strip
     trailing zeros the same way (see fmt below).
   * Text widths are estimated from a per-character table for IBM Plex
     Sans and the fixed 0.6 em advance of IBM Plex Mono, so the server
     can decide line breaks and the stacked-figure rule without a
     browser. Copy CHAR_WIDTH verbatim.
   * renderDialSVG() is the reference output. A Jinja macro can either
     call the Python port and emit the same SVG, or loop over the
     returned primitives itself.
   ===================================================================== */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ScopeGeometry = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ---------- Numbers and paths ---------- */

  /** Round to 2 decimals and print without trailing zeros (Python: f"{round(n,2):g}" is close; use the explicit form). */
  function fmt(n) { return (Math.round(n * 100) / 100).toString(); }
  function clamp01(x) { return Math.max(0, Math.min(1, x)); }
  /** Cubic ease-in-out — the motion curve cubic-bezier(0.65,0,0.35,1) approximated for scripted frames. */
  function easeInOut(x) { x = clamp01(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }

  /** Point at radius r and angle a (degrees clockwise from 12 o'clock) around (cx, cy). */
  function polar(cx, cy, r, a) { const t = a * Math.PI / 180; return [cx + r * Math.sin(t), cy - r * Math.cos(t)]; }
  /** Radial line at angle a from r1 to r2. */
  function radial(cx, cy, a, r1, r2) { const p = polar(cx, cy, r1, a), q = polar(cx, cy, r2, a); return `M${fmt(p[0])} ${fmt(p[1])}L${fmt(q[0])} ${fmt(q[1])}`; }
  /** Arc on radius r from a1 to a2 (clockwise). */
  function arc(cx, cy, r, a1, a2) {
    if (a2 - a1 < 0.2) return '';
    const p = polar(cx, cy, r, a1), q = polar(cx, cy, r, a2);
    return `M${fmt(p[0])} ${fmt(p[1])}A${fmt(r)} ${fmt(r)} 0 ${a2 - a1 > 180 ? 1 : 0} 1 ${fmt(q[0])} ${fmt(q[1])}`;
  }
  /** Full circle as a path (two half arcs). */
  function circle(cx, cy, r) { return `M${fmt(cx - r)} ${fmt(cy)}a${fmt(r)} ${fmt(r)} 0 1 0 ${fmt(2 * r)} 0a${fmt(r)} ${fmt(r)} 0 1 0 ${fmt(-2 * r)} 0`; }
  /** Annular wedge between radii r1 < r2 and angles a1 < a2 (closed path; a full circle becomes a ring). */
  function wedge(cx, cy, a1, a2, r1, r2) {
    if (a2 - a1 >= 359.9) return circle(cx, cy, r2) + circle(cx, cy, r1);
    const p1 = polar(cx, cy, r2, a1), p2 = polar(cx, cy, r2, a2), p3 = polar(cx, cy, r1, a2), p4 = polar(cx, cy, r1, a1);
    const lg = a2 - a1 > 180 ? 1 : 0;
    return `M${fmt(p1[0])} ${fmt(p1[1])}A${fmt(r2)} ${fmt(r2)} 0 ${lg} 1 ${fmt(p2[0])} ${fmt(p2[1])}L${fmt(p3[0])} ${fmt(p3[1])}A${fmt(r1)} ${fmt(r1)} 0 ${lg} 0 ${fmt(p4[0])} ${fmt(p4[1])}Z`;
  }

  /* ---------- Text measurement ---------- */

  /** IBM Plex Sans 500 advance widths in em, by character class. Close enough to decide line breaks. */
  const CHAR_WIDTH = { space: 0.25, narrow: 0.25, punct: 0.27, semi: 0.34, wide: 0.85, cap: 0.64, digit: 0.6, other: 0.55 };
  function sansCharEm(ch) {
    if (ch === ' ') return CHAR_WIDTH.space;
    if ('iljI|!'.indexOf(ch) >= 0) return CHAR_WIDTH.narrow;
    if ('.,:;\'’'.indexOf(ch) >= 0) return CHAR_WIDTH.punct;
    if ('frt()[]'.indexOf(ch) >= 0) return CHAR_WIDTH.semi;
    if ('mwMW'.indexOf(ch) >= 0) return CHAR_WIDTH.wide;
    if (ch >= 'A' && ch <= 'Z') return CHAR_WIDTH.cap;
    if (ch >= '0' && ch <= '9') return CHAR_WIDTH.digit;
    return CHAR_WIDTH.other;
  }
  /** Width in px of a string in IBM Plex Sans at size px. */
  function sansWidth(s, size) { let w = 0; for (const ch of s) w += sansCharEm(ch); return w * size; }
  /** Width in px of a string in IBM Plex Mono at size px (every glyph is 0.6 em). */
  function monoWidth(s, size) { return [...s].length * 0.6 * size; }

  /* ---------- The dial ---------- */

  /** Sizes. Phone: 260 px dial on a 358 px stage. Desktop: 440 px dial on a 640 × 560 stage. */
  const SIZES = {
    phone: { stageW: 358, stageH: 358, R: 130, nameSize: 11, nameLine: 14, edge: 187, figSizesHome: [22, 18], figSizesChapter: [18, 15] },
    desktop: { stageW: 640, stageH: 560, R: 220, nameSize: 13, nameLine: 17, edge: 312, figSizesHome: [32, 22], figSizesChapter: [22, 18] }
  };
  // `edge`: how far a name may run from the stage centre (phone: to 8 px from a 390 px screen edge).

  /**
   * Radii, scaled from the 300-unit master drawing (outer ring at 149.5).
   * Returns px values for a dial of outer radius R.
   */
  function radii(R) {
    const u = R / 150;
    return {
      u,
      outer: 149.5 * u,        // outer hairline ring
      tickEnd: 149 * u,        // all ticks end here
      minorStart: 145.5 * u,   // minor tick, every 2.5°
      midStart: 142.5 * u,     // mid tick, every 30°
      majorStart: 139.5 * u,   // major tick, at each sector divider
      inner: 137 * u,          // inner ring — the arc runs on it
      divStart: 70 * u,        // dividers stop short of the centre ring...
      divEnd: 132 * u,         // ...and of the inner ring
      ring: 64 * u,            // fine ring around the centre disc
      disc: 60 * u             // centre disc
    };
  }

  /**
   * Sector layout.
   * Home: four chapters, dividers at 0/90/180/270 — the midpoints fall on the diagonals.
   * Chapter: n facts divide the full circle with fact 1 centred at twelve o'clock,
   *   except n = 4, which uses the diagonals (dividers at 0/90/180/270).
   *   n = 2 → top and bottom; n = 3 → twelve, four and eight; n = 5 → every 72°.
   */
  function sectors(n, isHome) {
    const span = 360 / n;
    const offset = (isHome || n === 4) ? 0 : -span / 2;
    const out = [];
    for (let i = 0; i < n; i++) {
      const a1 = offset + i * span;
      out.push({ index: i, start: a1, end: a1 + span, mid: a1 + span / 2 });
    }
    return { span, offset, dividers: out.map((s) => s.start), slices: out };
  }

  /**
   * Tick marks for the bezel. Every 2.5°; three weights:
   *   major at each divider, mid every 30° (not on a divider), minor otherwise.
   * `rotation` turns the whole bezel (used by scope-in).
   */
  function ticks(cx, cy, rr, dividers, rotation) {
    rotation = rotation || 0;
    const norm = (a) => ((a % 360) + 360) % 360;
    const isDiv = (a) => dividers.some((d) => Math.abs(norm(a) - norm(d)) < 0.01);
    let minor = '', mid = '', major = '';
    for (let j = 0; j < 144; j++) {
      const a = j * 2.5;
      if (isDiv(a)) continue;
      if (a % 30 === 0) mid += radial(cx, cy, a + rotation, rr.midStart, rr.tickEnd);
      else minor += radial(cx, cy, a + rotation, rr.minorStart, rr.tickEnd);
    }
    dividers.forEach((a) => { major += radial(cx, cy, a + rotation, rr.majorStart, rr.tickEnd); });
    return { minor, mid, major };
  }

  /**
   * Slice name: upright, never curved. Sits just outside the bezel at the slice's arc
   * midpoint, joined to the rim by a 12 px hairline leader.
   *   right half  → left-aligned, starts 4 px after the leader
   *   left half   → right-aligned, ends 4 px before the leader
   *   12 or 6 o'clock (|sin| < 0.26) → centred above / below the leader
   * Two lines at most; only names in `threeLineNames` may take three (phone).
   * Returns the leader path, the lines and an anchor point for the first line's box.
   */
  function nameLabel(name, mid, cx, cy, rr, size, opts) {
    opts = opts || {};
    const s = Math.sin(mid * Math.PI / 180), c = Math.cos(mid * Math.PI / 180);
    const leaderStart = rr.outer + 2, leaderEnd = rr.outer + 2 + 12;
    const e = polar(cx, cy, leaderEnd, mid);
    const centred = Math.abs(s) < 0.26;
    const avail = centred ? Infinity : size.edge - Math.abs(e[0] - cx) - 4;
    const w = (t) => sansWidth(t, size.nameSize);
    let lines = [name];
    const tooWideCentred = centred && w(name) > (size.R > 150 ? 260 : 170);
    if (w(name) > avail || tooWideCentred) {
      const words = name.split(' ');
      let best = null, bw = Infinity;
      for (let j = 1; j < words.length; j++) {
        const L = [words.slice(0, j).join(' '), words.slice(j).join(' ')];
        const m = Math.max(w(L[0]), w(L[1]));
        if (m < bw) { bw = m; best = L; }
      }
      if (best) lines = best;
      const allowThree = (opts.threeLineNames || []).indexOf(name) >= 0;
      if (!centred && allowThree && Math.max(...lines.map(w)) > avail) {
        let b3 = null, m3 = Infinity;
        for (let a1 = 1; a1 < words.length - 1; a1++) for (let a2 = a1 + 1; a2 < words.length; a2++) {
          const L = [words.slice(0, a1).join(' '), words.slice(a1, a2).join(' '), words.slice(a2).join(' ')];
          const m = Math.max(...L.map(w)); if (m < m3) { m3 = m; b3 = L; }
        }
        if (b3) lines = b3;
      }
    }
    const h = lines.length * size.nameLine;
    let align, x = e[0], top;
    if (centred) { align = 'center'; top = c > 0 ? e[1] - 3 - h : e[1] + 3; }
    else if (s > 0) { align = 'left'; x = e[0] + 4; top = e[1] - h / 2; }
    else { align = 'right'; x = e[0] - 4; top = e[1] - h / 2; }
    return { lines, align, x, top, lineHeight: size.nameLine, leader: radial(cx, cy, mid, leaderStart, leaderEnd) };
  }

  /**
   * Stacked-figure rule.
   * A slice figure sets on one line where it fits. Where the wedge is too narrow it
   * sets on purpose as a stacked pair: the head at the slice-figure size, the rest
   * beneath in the 11 px mono label size, both centred on the bisector.
   *   "[N] of [N]"     → "[N]" over "of [N]"
   *   "10 trades"      → "10" over "trades"
   *   "[N] · [N] min"  → "[N] · [N]" over "min"   (the dot is set close: word-spacing −0.45 em)
   * Returns the possible stacked split, or null if the figure has no space.
   */
  function stackedSplit(fig) {
    const k = fig.indexOf(' of ');
    if (k > 0) return [fig.slice(0, k), fig.slice(k + 1)];
    const j = fig.lastIndexOf(' ');
    return j > 0 ? [fig.slice(0, j), fig.slice(j + 1)] : null;
  }

  /**
   * The block a slice's contents occupy. Rows, top to bottom:
   *   number (11 px mono, own line) · 4 px · figure head · [figure tail, 11 px] · 3 px · mini chart 36×14 (chapters)
   * A result state replaces the figure with "—" and a two-line state label.
   */
  function sliceBlock(item, figSize, stacked) {
    const state = item.state || '';
    const split = !state && stacked ? stackedSplit(item.figure) : null;
    const head = state ? '—' : (split ? split[0] : item.figure);
    const tail = split ? split[1] : '';
    const tight = head.indexOf(' · ') > 0;
    const headW = monoWidth(head, figSize) - (tight ? 2 * 0.45 * figSize : 0);
    const tailW = monoWidth(tail, 11);
    const lh = Math.round(figSize * 1.15);
    const rowA = 13 + 4 + lh + (tail ? 13 : 0);
    const rowB = state ? 28 : (item.chart ? 14 : 0);
    const w = Math.max(headW, tailW, rowB ? (state ? 66 : 36) : 0, 8);
    return { head, tail, tight, figSize, lineHeight: lh, rowA, rowB, w, h: rowA + (rowB ? 3 + rowB : 0) };
  }

  /** Clearance (px, negative = collision) of a block centred on slice i's bisector at radius rc. */
  function blockClearance(slice, span, rc, b, rr) {
    const s = Math.sin(slice.mid * Math.PI / 180), c = -Math.cos(slice.mid * Math.PI / 180);
    const px = rc * s, py = rc * c, x0 = px - b.w / 2, x1 = px + b.w / 2, y0 = py - b.h / 2, y1 = py + b.h / 2;
    const corners = [[x0, y0], [x1, y0], [x0, y1], [x1, y1]];
    const nx = Math.max(x0, Math.min(0, x1)), ny = Math.max(y0, Math.min(0, y1));
    let m = Math.min(Math.hypot(nx, ny) - rr.ring - 5, rr.inner - 4 - Math.max(...corners.map((q) => Math.hypot(q[0], q[1]))));
    if (span < 359) [slice.start, slice.end].forEach((a) => {
      const ax = Math.sin(a * Math.PI / 180), ay = -Math.cos(a * Math.PI / 180);
      const side = Math.sign(ax * py - ay * px) || 1;
      corners.forEach((q) => { if (q[0] * ax + q[1] * ay < 0) return; m = Math.min(m, (ax * q[1] - ay * q[0]) * side - 4); });
    });
    return m;
  }

  /**
   * Lay out every slice's contents.
   * One figure size per view (largest that fits). Every slice starts on one line; the
   * slice with the least clearance switches to its stacked form until all fit; any
   * stacked figure that would now fit on one line goes back. One shared radius when
   * every slice fits at it; otherwise each slice keeps the row grid at its own radius.
   */
  function layoutContents(items, sec, rr, figSizes) {
    const best = (blocks) => {
      let br = (rr.divStart + rr.divEnd) / 2, bs = -Infinity;
      for (let rc = rr.ring; rc <= rr.inner; rc += 0.5) {
        let sc = Infinity; blocks.forEach((b, i) => { sc = Math.min(sc, blockClearance(sec.slices[i], sec.span, rc, b, rr)); });
        if (sc > bs) { bs = sc; br = rc; }
      }
      return { rc: br, score: bs };
    };
    const canStack = (it) => !it.state && !!stackedSplit(it.figure);
    for (let si = 0; si < figSizes.length; si++) {
      const fs = figSizes[si];
      const forms = items.map(() => false);
      let blocks = items.map((it) => sliceBlock(it, fs, false)), r = best(blocks);
      for (let pass = 0; pass < 8 && r.score < 0; pass++) {
        let wi = -1, wv = Infinity;
        blocks.forEach((b, i) => { if (!forms[i] && canStack(items[i])) { const cl = blockClearance(sec.slices[i], sec.span, r.rc, b, rr); if (cl < wv) { wv = cl; wi = i; } } });
        if (wi < 0) break;
        forms[wi] = true; blocks = items.map((it, i) => sliceBlock(it, fs, forms[i])); r = best(blocks);
      }
      if (r.score >= 0) {
        items.forEach((it, i) => {
          if (!forms[i]) return;
          const f2 = forms.slice(); f2[i] = false;
          const b2 = items.map((x, j) => sliceBlock(x, fs, f2[j])), r2 = best(b2);
          if (r2.score >= 0) { forms[i] = false; blocks = b2; r = r2; }
        });
        return { blocks, radius: blocks.map(() => r.rc), stacked: forms, figSize: fs };
      }
      if (si === figSizes.length - 1) {
        const own = blocks.map((b, i) => { let br = r.rc, bs = -Infinity; for (let rc = rr.ring; rc <= rr.inner; rc += 0.5) { const cl = blockClearance(sec.slices[i], sec.span, rc, b, rr); if (cl > bs) { bs = cl; br = rc; } } return br; });
        return { blocks, radius: own, stacked: forms, figSize: fs };
      }
    }
  }

  /**
   * Build the whole dial.
   * view = {
   *   kind: 'home' | 'chapter',
   *   items: [{ name, figure, href, chart?: 'worst'|..., state?: '' | 'not-enough' | 'not-in-file', opened?: bool }],
   *   centre: home → { figure, caption }  |  chapter → { name, scopeHref },
   * }
   * size: 'phone' | 'desktop'
   * Returns every primitive needed to draw it (see renderDialSVG for use).
   */
  function buildDial(view, sizeName, opts) {
    opts = opts || {};
    const size = SIZES[sizeName || 'phone'];
    const cx = size.stageW / 2, cy = size.stageH / 2, rr = radii(size.R);
    const isHome = view.kind === 'home';
    const sec = sectors(view.items.length, isHome);
    const t = ticks(cx, cy, rr, sec.dividers, 0);
    const lay = layoutContents(view.items, sec, rr, isHome ? size.figSizesHome : size.figSizesChapter);
    const slices = sec.slices.map((sl, i) => {
      const it = view.items[i], b = lay.blocks[i], q = polar(cx, cy, lay.radius[i], sl.mid);
      const top = q[1] - b.h / 2;
      return {
        index: i, number: String(i + 1), name: it.name, href: it.href, state: it.state || '', opened: !!it.opened,
        start: sl.start, end: sl.end, mid: sl.mid,
        hit: wedge(cx, cy, sl.start, sl.end, rr.ring, rr.outer),            // the whole slice is the tap target
        focusRing: wedge(cx, cy, sl.start + 1.5, sl.end - 1.5, rr.divStart - 4 * rr.u, rr.inner - 2),
        lift: wedge(cx, cy, sl.start, sl.end, rr.divStart - 6 * rr.u, rr.inner),  // pressed: white at 10 %
        hatch: it.state === 'not-enough' ? wedge(cx, cy, sl.start, sl.end, rr.divStart, rr.inner) : '',
        dashed: it.state === 'not-in-file' ? wedge(cx, cy, sl.start + 1.5, sl.end - 1.5, rr.divStart + 3, rr.inner - 3) : '',
        openedMark: it.opened ? polar(cx, cy, rr.inner - 3 * rr.u, sl.mid) : null,
        contents: {
          x: q[0],
          numberY: top,                                  // top of the 11 px number line
          headY: top + 17,                               // top of the figure line
          tailY: top + 17 + b.lineHeight,                // top of the 11 px tail line (stacked only)
          chartY: top + b.rowA + 3,                      // top of the mini chart / state label
          head: b.head, tail: b.tail, tight: b.tight, figSize: b.figSize, lineHeight: b.lineHeight,
          chart: it.state ? '' : (it.chart || ''),
          tone: it.state ? 'state' : (/^−₹|^-₹/.test(it.figure) ? 'rupee' : 'plain')
        },
        label: nameLabel(it.name, sl.mid, cx, cy, rr, size, opts)
      };
    });
    return {
      size: sizeName || 'phone', stageW: size.stageW, stageH: size.stageH, cx, cy, R: size.R, radii: rr,
      kind: view.kind, centre: view.centre || {},
      outerRing: circle(cx, cy, rr.outer), innerRing: circle(cx, cy, rr.inner),
      ticks: t,
      dividers: sec.dividers.map((a) => radial(cx, cy, a, rr.divStart, rr.divEnd)),
      arc: isHome ? '' : arc(cx, cy, rr.inner, -43, 43),     // inside a chapter: at the top, on the inner ring
      disc: circle(cx, cy, rr.disc), centreRing: circle(cx, cy, rr.ring),
      slices, figSize: lay.figSize
    };
  }

  /* ---------- Reference SVG ---------- */

  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  /** Lines of text as an SVG <text> with tspans; `top` is the top of the first line box. */
  function textBlock(lines, x, top, lineHeight, size, align, cls) {
    const anchor = align === 'left' ? 'start' : align === 'right' ? 'end' : 'middle';
    const base = top + lineHeight / 2 + size * 0.35;   // optical centre of the line box
    return `<text class="${cls}" x="${fmt(x)}" y="${fmt(base)}" text-anchor="${anchor}">` +
      lines.map((l, i) => `<tspan x="${fmt(x)}" dy="${i ? lineHeight : 0}">${esc(l)}</tspan>`).join('') + '</text>';
  }

  /**
   * Render the dial as inline SVG. Class names match components.css (.scope__*).
   * miniCharts: optional map kind → inner SVG markup for a 36 × 14 chart.
   * Values in item.figure / centre are written as given — pass Jinja placeholders
   * (e.g. "{{ ch1_figure }}") to get a template.
   */
  function renderDialSVG(d, miniCharts) {
    miniCharts = miniCharts || {};
    const o = [];
    const pad = 40; // room for names outside the stage box on phone
    o.push(`<svg class="scope__svg" viewBox="${-pad} 0 ${d.stageW + 2 * pad} ${d.stageH}" width="${d.stageW + 2 * pad}" height="${d.stageH}" role="img" aria-label="${d.kind === 'home' ? 'The Scope: four chapters of your story' : 'The Scope inside this chapter'}">`);
    o.push('<defs><pattern id="scope-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0V5" class="scope__hatch-line"/></pattern></defs>');
    o.push(`<path class="scope__outer" d="${d.outerRing}"/>`);
    d.slices.forEach((s) => { if (s.hatch) o.push(`<path class="scope__state-hatch" d="${s.hatch}"/>`); if (s.dashed) o.push(`<path class="scope__state-dashed" d="${s.dashed}"/>`); });
    o.push(`<g class="scope__bezel"><path class="scope__tick scope__tick--minor" d="${d.ticks.minor}"/><path class="scope__tick scope__tick--mid" d="${d.ticks.mid}"/><path class="scope__tick scope__tick--major" d="${d.ticks.major}"/></g>`);
    o.push(`<path class="scope__inner" d="${d.innerRing}"/>`);
    if (d.arc) o.push(`<path class="scope__arc" d="${d.arc}"/>`);
    o.push(`<g class="scope__dividers">${d.dividers.map((p) => `<path class="scope__divider" d="${p}"/>`).join('')}</g>`);
    d.slices.forEach((s) => {
      const c = s.contents;
      o.push(`<a class="scope__slice${s.state ? ' scope__slice--' + s.state : ''}" href="${s.href}" aria-label="${esc(s.number + '. ' + s.name + '.')}">`);
      o.push(`<path class="scope__hit" d="${s.hit}"/><path class="scope__lift" d="${s.lift}"/><path class="scope__focus" d="${s.focusRing}"/>`);
      if (s.openedMark) o.push(`<circle class="scope__opened" cx="${fmt(s.openedMark[0])}" cy="${fmt(s.openedMark[1])}" r="${d.size === 'phone' ? 2 : 2.5}"/>`);
      o.push(textBlock([s.number], c.x, c.numberY, 13, 11, 'center', 'scope__number'));
      o.push(textBlock([c.head], c.x, c.headY, c.lineHeight, c.figSize, 'center', `scope__figure scope__figure--s${c.figSize} scope__figure--${c.tone}${c.tight ? ' scope__figure--tight' : ''}`));
      if (c.tail) o.push(textBlock([c.tail], c.x, c.tailY, 13, 11, 'center', `scope__figure-tail scope__figure--${c.tone}`));
      if (s.state) o.push(textBlock(s.state === 'not-enough' ? ['not enough', 'trades yet'] : ['not in', 'your file'], c.x, c.chartY, 14, 11, 'center', 'scope__state'));
      else if (c.chart) o.push(`<g class="scope__mini chart chart--on-navy" transform="translate(${fmt(c.x - 18)} ${fmt(c.chartY)})">${miniCharts[c.chart] || ''}</g>`);
      o.push('</a>');
      o.push(`<path class="scope__leader" d="${s.label.leader}"/>`);
      o.push(textBlock(s.label.lines, s.label.x, s.label.top, s.label.lineHeight, 11, s.label.align, 'scope__name'));
    });
    o.push(`<path class="scope__disc" d="${d.disc}"/><path class="scope__centre-ring" d="${d.centreRing}"/>`);
    const R = d.radii;
    if (d.kind === 'home') {
      o.push(textBlock([d.centre.figure || '{{ five_day_share_percent }}%'], d.cx, d.cy - (d.size === 'phone' ? 26 : 38), d.size === 'phone' ? 24 : 34, d.size === 'phone' ? 22 : 32, 'center', 'scope__centre-figure'));
      o.push(textBlock(['of your result', 'in five days'], d.cx, d.cy + 2, 13, 11, 'center', 'scope__centre-caption'));
    } else {
      const words = (d.centre.name || '').split(' '), maxW = R.disc * 1.55, fs = d.size === 'phone' ? 11 : 15, lines = []; let cur = '';
      words.forEach((w) => { const t = cur ? cur + ' ' + w : w; if (sansWidth(t, fs) > maxW && cur) { lines.push(cur); cur = w; } else cur = t; }); if (cur) lines.push(cur);
      const lh = Math.round(fs * 1.25), tot = lines.length * lh + 4 + 13;
      o.push(textBlock(lines, d.cx, d.cy - tot / 2, lh, fs, 'center', 'scope__centre-name'));
      o.push(`<a class="scope__centre-link" href="${d.centre.scopeHref || '/scope'}" aria-label="Scope out to all four chapters">${textBlock(['Scope'], d.cx, d.cy + tot / 2 - 13, 13, 11, 'center', 'scope__centre-scope')}<circle cx="${fmt(d.cx)}" cy="${fmt(d.cy)}" r="${fmt(R.disc)}" class="scope__centre-hit"/></a>`);
    }
    o.push('</svg>');
    return o.join('');
  }

  /* ---------- Lens (56 px) ---------- */

  /** The lens in the path bar: same bezel, dividers and centre ring as the chapter dial, the fact's wedge lit. */
  function buildLens(nFacts, factIndex) {
    const c = 28, sec = sectors(nFacts, false), span = sec.span;
    const norm = (a) => ((a % 360) + 360) % 360;
    const divs = sec.dividers.map(norm);
    let minor = '', mid = '', major = '', div = '';
    for (let a = 0; a < 360; a += 10) { if (divs.indexOf(a) >= 0) continue; if (a % 30 === 0) mid += radial(c, c, a, 24, 27); else minor += radial(c, c, a, 25, 27); }
    divs.forEach((a) => { major += radial(c, c, a, 22.5, 27); div += radial(c, c, a, 11.5, 20); });
    const s = sec.slices[factIndex];
    return { minor, mid, major, div, lit: wedge(c, c, s.start, s.end, 10.5, 21.5), arc: arc(c, c, 21.5, -43, 43), outer: circle(c, c, 27.5), inner: circle(c, c, 21.5), ring: circle(c, c, 10.5), disc: circle(c, c, 9) };
  }

  /* ---------- Scope-in timeline (for scripted frames; CSS covers the live motion) ---------- */

  /**
   * State of the scope-in transition at t ms (0…480). Scope-out is the same at 480 − t.
   *   0–120   tapped wedge lifts one tone (0 → 10 %), others fade to 20 %, names fade out
   *   120–320 the whole dial turns so the tapped wedge's midpoint is at twelve o'clock
   *   320–480 the wedge opens to the full circle; new dividers draw in from the centre 40 ms apart;
   *           figures count up; the arc draws in; new names fade in
   *   centre text: old fades out over 0–240, new fades in over 240–480 — never two at once
   */
  function scopeInAt(t, tapMid, nNew) {
    return {
      rotation: -tapMid * easeInOut((t - 120) / 200),
      liftOpacity: 0.1 * clamp01(t / 120) * (t < 400 ? 1 : 1 - clamp01((t - 400) / 80)),
      liftHalfWidth: 45 + 135 * easeInOut((t - 320) / 120),
      otherOpacity: t < 120 ? 1 - 0.8 * clamp01(t / 120) : 0.2 * (1 - clamp01((t - 320) / 60)),
      oldNames: 1 - clamp01(t / 120),
      oldCentre: 1 - clamp01(t / 240),
      newCentre: clamp01((t - 240) / 240),
      dividerProgress: Array.from({ length: nNew }, (_, j) => easeInOut((t - 320 - 40 * j) / 80)),
      arcProgress: easeInOut((t - 320) / 160),
      newContents: clamp01((t - 380) / 100),
      newNames: clamp01((t - 400) / 80)
    };
  }

  /* ---------- Charts ---------- */
  /*
   * Every chart returns { w, h, parts } where parts is a list of
   * { role, d } — role is a CSS class suffix (.chart__<role>) that sets the colour:
   *   ink (emphasis), light (context), faint (secondary), red / green (signed rupees),
   *   hatch (not enough / not in file), axis, stroke (brackets, medians), dash (reference line).
   * Data are plain numbers. `mini` charts (36 × 14) use the same functions with small w/h.
   */
  const R2 = (x, y, w, h) => `M${fmt(x)} ${fmt(y)}h${fmt(w)}v${fmt(h)}h${fmt(-w)}Z`;
  const DOT = (x, y, r) => circle(x, y, r);
  function partsOf(map) { return Object.keys(map).filter((k) => map[k]).map((k) => ({ role: k, d: map[k] })); }

  const charts = {
    /** Net (gross) per trading day; the five worst days in ink, the rest light. */
    worst(dailyNet, w, h) {
      const n = dailyNet.length, bw = w / n, max = Math.max(...dailyNet.map(Math.abs), 1), z = h * 0.45;
      const order = dailyNet.map((v, i) => i).sort((a, b) => dailyNet[a] - dailyNet[b]).slice(0, 5);
      const m = { ink: '', light: '', axis: `M0 ${fmt(z)}H${w}` };
      dailyNet.forEach((v, i) => { const bh = Math.max(0.6, Math.abs(v) / max * h * 0.5); const r = R2(i * bw + bw * 0.15, v > 0 ? z - bh : z, bw * 0.7, bh); if (order.indexOf(i) >= 0) m.ink += r; else m.light += r; });
      return { w, h, parts: partsOf(m) };
    },
    /** The five worst days as a share of the whole result, with a bracket for the whole period. share ∈ (0,1]. */
    share(share, w, h, mini) {
      const bh = mini ? h * 0.7 : h * 0.42, y0 = mini ? h * 0.15 : h * 0.08, m = { ink: R2(0, y0, w * share, bh), light: R2(w * share + 1, y0, w * (1 - share) - 1, bh), stroke: '' };
      if (!mini) { const y = h * 0.8, t = h * 0.13; m.stroke = `M0.5 ${fmt(y - t)}V${fmt(y + t)}M0.5 ${fmt(y)}H${fmt(w - 0.5)}M${fmt(w - 0.5)} ${fmt(y - t)}V${fmt(y + t)}`; }
      return { w, h, parts: partsOf(m) };
    },
    /** Best five (green, to the right) and worst five (red, to the left) trades. */
    money(best5, worst5, w, h) {
      const all = best5.concat(worst5.map(Math.abs)), max = Math.max(...all, 1), n = 10, rh = h / n, cx = w / 2, m = { green: '', red: '', axis: `M${fmt(cx)} 0V${fmt(h)}` };
      best5.forEach((v, i) => { m.green += R2(cx, i * rh + rh * .2, v / max * cx * .96, rh * .6); });
      worst5.forEach((v, i) => { const l = Math.abs(v) / max * cx * .96; m.red += R2(cx - l, (i + 5) * rh + rh * .2, l, rh * .6); });
      return { w, h, parts: partsOf(m) };
    },
    /** Minutes open, one dot per trade: winners (ink) above, losers (faint) below, a median tick on each. */
    hold(winMins, lossMins, maxMins, w, h, mini) {
      const ys = [h * 0.3, h * 0.72], r = mini ? 1.3 : 3.2, t = mini ? 3 : 8, med = (a) => { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : 0; };
      const X = (v) => Math.min(1, v / maxMins) * w;
      const m = { ink: winMins.map((v) => DOT(X(v), ys[0], r)).join(''), faint: lossMins.map((v) => DOT(X(v), ys[1], r)).join(''), stroke: `M${fmt(X(med(winMins)))} ${fmt(ys[0] - t)}V${fmt(ys[0] + t)}M${fmt(X(med(lossMins)))} ${fmt(ys[1] - t)}V${fmt(ys[1] + t)}`, axis: `M0 ${fmt(ys[0])}H${w}M0 ${fmt(ys[1])}H${w}` };
      return { w, h, parts: partsOf(m) };
    },
    /** Winners / losers / level as one bar. */
    strike(winners, losers, level, w, h, mini) {
      const tot = Math.max(1, winners + losers + level), bh = mini ? h * 0.7 : h * 0.4, y0 = mini ? h * 0.15 : h * 0.3;
      const a = w * winners / tot, b = w * losers / tot;
      return { w, h, parts: partsOf({ ink: R2(0, y0, a, bh), faint: R2(a + 1, y0, b - 1, bh), hatch: level ? R2(a + b + 1, y0, w - a - b - 1, bh) : '' }) };
    },
    /** One square per trade in order; the longest losing run in ink, bracketed. */
    run(nTrades, runStart, runLength, w, h, mini) {
      const g = w / nTrades, s = Math.min(mini ? 3 : 7, g * 0.8), m = { ink: '', light: '', stroke: '' };
      for (let i = 0; i < nTrades; i++) { const r = R2(i * g + (g - s) / 2, h * 0.5 - s / 2 - (mini ? 0 : 6), s, s); if (i >= runStart && i < runStart + runLength) m.ink += r; else m.light += r; }
      if (!mini) m.stroke = `M${fmt(runStart * g + 2)} ${fmt(h * 0.5 + 6)}V${fmt(h * 0.5 + 12)}H${fmt((runStart + runLength) * g - 2)}V${fmt(h * 0.5 + 6)}`;
      return { w, h, parts: partsOf(m) };
    },
    /** Net (gross) by the hour a trade was opened; hours with few trades hatched. */
    clock(hourNet, fewHours, w, h) {
      const n = hourNet.length, bw = w / n, z = h * 0.5, max = Math.max(...hourNet.map(Math.abs), 1), m = { green: '', red: '', hatch: '', axis: `M0 ${fmt(z)}H${w}` };
      hourNet.forEach((v, i) => { const bh = Math.max(0.6, Math.abs(v) / max * h * 0.46); const r = R2(i * bw + bw * 0.18, v > 0 ? z - bh : z, bw * 0.64, bh); if (fewHours.indexOf(i) >= 0) m.hatch += r; else if (v > 0) m.green += r; else m.red += r; });
      return { w, h, parts: partsOf(m) };
    },
    /** Average result after two straight losses (top) against every other qualifying trade (bottom). */
    down(afterTwo, others, w, h, mini) {
      const max = Math.max(Math.abs(afterTwo), Math.abs(others), 1), bh = mini ? h * 0.3 : h * 0.26;
      return { w, h, parts: partsOf({ red: R2(0, mini ? h * 0.08 : h * 0.12, w * Math.abs(afterTwo) / max, bh) + R2(0, mini ? h * 0.58 : h * 0.6, w * Math.abs(others) / max, bh), axis: `M0.5 0V${h}` }) };
    },
    /** Trades per day; the busiest day in ink; the normal day as a dashed line. */
    busy(dayCounts, normal, w, h) {
      const n = dayCounts.length, bw = w / n, max = Math.max(...dayCounts, 1), bi = dayCounts.indexOf(max), m = { ink: '', light: '', dash: `M0 ${fmt(h - normal / max * h * 0.9)}H${w}` };
      dayCounts.forEach((v, i) => { const bh = v / max * h * 0.9; const r = R2(i * bw + bw * 0.18, h - bh, bw * 0.64, bh); if (i === bi) m.ink += r; else m.light += r; });
      return { w, h, parts: partsOf(m) };
    },
    /** Rows read (ink) and rows set aside (hatched). */
    read(rowsRead, rowsTotal, w, h, mini) {
      const f = rowsRead / Math.max(1, rowsTotal), bh = mini ? h * 0.7 : h * 0.4, y0 = mini ? h * 0.15 : h * 0.3;
      return { w, h, parts: partsOf({ ink: R2(0, y0, w * f, bh), hatch: f < 1 ? R2(w * f + 1, y0, w * (1 - f) - 1, bh) : '' }) };
    },
    /** Trades by what they were measured against: budget, stop, premium, nothing usable. */
    risk(budget, stop, premium, nothing, w, h, mini) {
      const tot = Math.max(1, budget + stop + premium + nothing), bh = mini ? h * 0.7 : h * 0.4, y0 = mini ? h * 0.15 : h * 0.3;
      const a = w * budget / tot, b = w * stop / tot, c = w * premium / tot;
      return { w, h, parts: partsOf({ ink: R2(0, y0, a, bh), faint: R2(a + 1, y0, b - 1, bh), light: R2(a + b + 1, y0, c - 1, bh), hatch: R2(a + b + c + 1, y0, w - a - b - c - 1, bh) }) };
    },
    /** "What we have not told you" has no data: four quiet lines, like an unwritten page. */
    notold(w, h, mini) {
      let light = ''; [1, 0.86, 0.94, 0.6].forEach((v, i) => { light += R2(0, (i + 0.5) * h / 4 - (mini ? 0.75 : 2), v * w, mini ? 1.5 : 4); });
      return { w, h, parts: partsOf({ light }) };
    }
  };

  /** Chart → SVG markup (inner parts only, or wrapped when `wrap` is true). */
  function renderChart(c, cls, wrap) {
    const inner = c.parts.map((p) => `<path class="chart__${p.role}" d="${p.d}"/>`).join('');
    return wrap ? `<svg class="chart ${cls || ''}" viewBox="0 0 ${c.w} ${c.h}" width="${c.w}" height="${c.h}" aria-hidden="true">${inner}</svg>` : inner;
  }

  /* ---------- Trade strip (the mark, and the trade record) ---------- */

  /**
   * A trade drawn to time: fills as ticks and dots at their times, the bar from first to last fill.
   * fillTimes are minutes since the trade's first fill; width is the strip width in px.
   */
  function tradeStrip(fillTimes, width, height) {
    height = height || 18;
    const span = Math.max(1, Math.max(...fillTimes) - Math.min(...fillTimes)), t0 = Math.min(...fillTimes);
    const xs = fillTimes.map((t) => 4 + (t - t0) / span * (width - 8));
    const base = height - 4.5;
    return {
      axis: `M0 ${fmt(base)}H${width}`,
      ticks: xs.map((x) => `M${fmt(x)} 5V${fmt(base - 1.5)}`).join(''),
      dots: xs.map((x) => circle(x, base, 3)).join(''),
      bar: `M${fmt(xs[0])} 3H${fmt(xs[xs.length - 1])}`,
      // motion: each fill lands 40 ms after the last, then a 160 ms pause, then the bar draws in 200 ms
      fillDelays: xs.map((_, i) => i * 40),
      barDelay: xs.length * 40 + 160
    };
  }

  return { fmt, clamp01, easeInOut, polar, radial, arc, circle, wedge, sansWidth, monoWidth, CHAR_WIDTH, SIZES, radii, sectors, ticks, nameLabel, stackedSplit, sliceBlock, blockClearance, layoutContents, buildDial, renderDialSVG, buildLens, scopeInAt, charts, renderChart, tradeStrip };
}));
