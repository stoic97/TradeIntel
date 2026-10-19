/* Which lines were read, and for how long. PRD decision 12.
 *
 * Sends a line's slug and a duration. Never a figure, never anything typed. Batched
 * and sent on leaving the page, so it costs the reader nothing while he reads.
 *
 * Every call is wrapped: a telemetry failure must not break the page it measures.
 */
(function () {
  "use strict";
  var queue = [];
  var seen = new WeakMap();

  function push(surface, key, event, durationMs) {
    try {
      queue.push({
        surface: surface,
        key: key,
        event: event,
        duration_ms: typeof durationMs === "number" ? Math.round(durationMs) : undefined
      });
    } catch (e) { /* telemetry never breaks the page */ }
  }

  function flush() {
    if (!queue.length) return;
    var body = JSON.stringify({ events: queue.splice(0, queue.length) });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/events", new Blob([body], { type: "application/json" }));
      } else {
        fetch("/events", { method: "POST", body: body, keepalive: true,
                           headers: { "Content-Type": "application/json" } });
      }
    } catch (e) { /* telemetry never breaks the page */ }
  }

  try {
    /* A line is "read" once it has been on screen for a second. */
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var key = entry.target.getAttribute("data-dwell-line");
        if (!key) return;
        if (entry.isIntersecting) {
          seen.set(entry.target, Date.now());
        } else if (seen.has(entry.target)) {
          var ms = Date.now() - seen.get(entry.target);
          seen.delete(entry.target);
          if (ms > 1000) push("mirror_line", key, "view", ms);
        }
      });
    }, { threshold: 0.5 });

    document.querySelectorAll("[data-dwell-line]").forEach(function (el) {
      observer.observe(el);
    });

    document.addEventListener("click", function (ev) {
      var button = ev.target.closest && ev.target.closest("[data-line]");
      if (button) push("mirror_line", button.getAttribute("data-line"), "drawer_open");
    });

    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") flush();
    });
  } catch (e) { /* telemetry never breaks the page */ }
})();
