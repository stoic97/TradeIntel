# docs/design — what's here

Read `docs/product/scope_engineering_handoff_v1.md` first. If an image, a kit file or a canvas note disagrees with it, the handoff wins.

| Folder | What it is |
|---|---|
| `screens/` | Every artboard of the prototype as finally designed (27 Oct): the journey, the Scope (home, four chapters, 12 facts), edge states, desktop, motion strips, parts. Fonts in the images are stand-ins; the real fonts are IBM Plex Sans, IBM Plex Mono and Source Serif 4 |
| `scope-kit/` | The engineering kit from Claude Design: `tokens.css`, `components.css`, `components.html`, `motion.css`, `scope-geometry.js`, one Jinja template per screen in `screens/` and filled previews in `screens/preview/`. Open `components.html` and the previews in a browser |

**Two places where the kit is not what to build:**
- **Calculating:** the kit's README describes polling every 2 s. Don't poll; handoff §7 (decision D1) says how it works.
- **Routes:** the kit's README proposes routes; handoff §5 has the ones to use.

The live references are the two Claude Design canvases, **"PlusEV Scope Prototype"** (press Play) and **"PlusEV Scope Design System"**. Ask the founder to share them with you.
