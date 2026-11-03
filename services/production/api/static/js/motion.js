/* The Scope's motion (handoff 7 and 8, T6): what motion.css cannot do alone.
 *
 * The transitions themselves are cross-document View Transitions, played by
 * motion.css from the class the server puts on <html> (?enter=). A browser without
 * them switches instantly. This file adds four things around them:
 *
 *  1. Pressed. On pointerdown the tapped wedge lifts and the others fade, so the
 *     transition starts from that state (the kit's motion.css, "Pressed").
 *  2. One play per tap. Once a page is shown, ?enter=, ?tap= and ?fact= leave its
 *     address: a reload, a shared link or the back button must not replay the
 *     motion of a tap that did not happen. A page come back to - from the back
 *     button or the back-forward cache - drops its motion class and pressed state,
 *     so it shows as it was, not as it was left.
 *  3. Number count. A whole-number figure (62, 96%) counts up to its value once,
 *     600 ms, when the dial opens or a fact rises into place. The value is the
 *     server's, and is the page's text before and after: only the frames between
 *     are drawn here. A rupee figure, a decimal or a state is shown as it is.
 *  4. Reduced motion. Nothing counts; motion.css makes every transition a 120 ms
 *     crossfade.
 *
 * Every handler is wrapped: motion is never allowed to break the page it moves.
 */
(function (root) {
  "use strict";

  var MOTION = /(^|\s)vt-[a-z0-9-]+/g;
  var HINTS = ["enter", "tap", "fact"];
  var COUNT_MS = 600;
  var WHOLE = /^(\d{1,4})(%?)$/;
  var PRESS_MS = 1500;  // longer than any tap takes to leave the page

  /* The address without the motion hints; null when it carries none. */
  function withoutHints(href) {
    var url = new URL(href);
    var had = false;
    HINTS.forEach(function (name) {
      if (url.searchParams.has(name)) { url.searchParams.delete(name); had = true; }
    });
    return had ? url.pathname + url.search + url.hash : null;
  }

  /* A figure that may count: a whole number, optionally a percentage. */
  function countable(text) {
    var found = WHOLE.exec((text || "").trim());
    return found ? { to: parseInt(found[1], 10), suffix: found[2] } : null;
  }

  /* The figure t ms into the count: ease-out, ending exactly on the value. */
  function frame(to, t) {
    if (t >= COUNT_MS) return to;
    var p = Math.max(t, 0) / COUNT_MS;
    return Math.round(to * (1 - Math.pow(1 - p, 3)));
  }

  /* Which figures count for the motion that brought the page here. */
  function countSelector(className) {
    if (/(^|\s)vt-in(\s|$)/.test(className)) return ".scope__figure";
    if (/(^|\s)vt-lens(\s|$)/.test(className)) return ".fact__figure .num";
    return null;
  }

  var api = { withoutHints: withoutHints, countable: countable, frame: frame,
              countSelector: countSelector, COUNT_MS: COUNT_MS };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.scopeMotion = api;

  var doc = root.document;
  var html = doc.documentElement;

  function quiet() {
    try { return root.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch (e) { return true; }
  }

  function unpress() {
    var dials = doc.querySelectorAll(".scope.is-leaving, .scope.is-leaving-to-fact");
    Array.prototype.forEach.call(dials, function (dial) {
      dial.classList.remove("is-leaving", "is-leaving-to-fact");
    });
    Array.prototype.forEach.call(doc.querySelectorAll(".is-pressed"), function (el) {
      el.classList.remove("is-pressed");
    });
  }

  function still() {
    html.className = html.className.replace(MOTION, "").trim();
    if (!html.className) html.removeAttribute("class");
    unpress();
  }

  function count() {
    var selector = countSelector(html.className);
    if (!selector || quiet() || !root.requestAnimationFrame) return;
    var figures = [];
    Array.prototype.forEach.call(doc.querySelectorAll(selector), function (el) {
      var value = countable(el.textContent);
      if (value && value.to > 0 && !el.children.length) figures.push({ el: el, value: value, text: el.textContent });
    });
    if (!figures.length) return;
    var start = null;
    function step(now) {
      if (start === null) start = now;
      var t = now - start;
      figures.forEach(function (f) {
        f.el.textContent = t >= COUNT_MS ? f.text : frame(f.value.to, t) + f.value.suffix;
      });
      if (t < COUNT_MS) root.requestAnimationFrame(step);
    }
    root.requestAnimationFrame(step);
  }

  function arrivedBy() {
    try {
      if (root.navigation && root.navigation.activation) {
        return root.navigation.activation.navigationType;  // push, replace, reload, traverse
      }
      var entry = root.performance.getEntriesByType("navigation")[0];
      return entry ? { back_forward: "traverse" }[entry.type] || entry.type : "push";
    } catch (e) { return "push"; }
  }

  // Settled before the first frame where the browser says when that is (pagereveal,
  // which is why this file loads in <head> without defer), else once parsed.
  var settled = false;
  function settle() {
    if (settled) return;
    settled = true;
    try {
      var by = arrivedBy();
      if (by === "traverse" || by === "reload") still();
    } catch (e) { /* motion never breaks the page */ }
  }
  root.addEventListener("pagereveal", settle);

  // Counting needs the figures, so it waits for the page to be parsed.
  doc.addEventListener("DOMContentLoaded", function () {
    settle();
    try {
      count();
      var clean = withoutHints(root.location.href);
      if (clean !== null) root.history.replaceState(root.history.state, "", clean);
    } catch (e) { /* motion never breaks the page */ }
  });

  // Back to a page kept in the back-forward cache: as it was, not as it was left.
  root.addEventListener("pageshow", function (e) {
    try { if (e.persisted) still(); } catch (err) { /* never breaks the page */ }
  });

  doc.addEventListener("pointerdown", function (e) {
    try {
      var link = e.target.closest && e.target.closest("a.scope__slice, a.story-card");
      if (!link || e.button > 0) return;
      var href = link.getAttribute("href") || "";
      var slice = link;
      if (link.classList.contains("story-card")) {
        slice = Array.prototype.filter.call(doc.querySelectorAll("a.scope__slice"), function (s) {
          return s.getAttribute("href") === href;
        })[0];
      }
      var dial = slice && slice.closest(".scope");
      if (!dial) return;
      dial.classList.add("is-leaving");
      if (href.indexOf("enter=lens") !== -1) dial.classList.add("is-leaving-to-fact");
      slice.classList.add("is-pressed");
      // A tap that does not become a navigation (a scroll, a drag off the link)
      // must not leave the dial faded.
      root.setTimeout(unpress, PRESS_MS);
    } catch (err) { /* never breaks the page */ }
  });
  doc.addEventListener("pointercancel", function () {
    try { unpress(); } catch (err) { /* never breaks the page */ }
  });
})(typeof window !== "undefined" ? window : this);
