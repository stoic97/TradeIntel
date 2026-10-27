# docs/design — what's here and which to trust

Read `docs/product/scope_engineering_handoff_v1.md` first. If an image disagrees with it, the handoff wins.

| Folder | What it is | Trust it for |
|---|---|---|
| `screens/latest/` | The **final** Scope dial: Home, the four chapters, and the five motion strips (27 Oct, after every polish pass). Fonts are stand-ins; the real fonts are IBM Plex and Source Serif 4 | The look of the Scope stage and every transition |
| `screens/` | The full set of 81 screens (26 Oct), exported **before** the polish passes | The structure, the flow and the wording of every screen. **Not** the final look: body text was then muted blue, the gross line was a box, the stage was white, and the reveal, fact page, Calculating and dial names were redrawn after it. Handoff §7 has the final rules |
| `scope-kit/` | The engineering kit from Claude Design: `tokens.css`, `components.css`, `motion.css`, `scope-geometry.js`, one template per screen. **To be added** | The code form of the design system |

The live references are the two Claude Design canvases, **"PlusEV Scope Prototype"** (press Play) and **"PlusEV Scope Design System"**. Ask the founder to share them with you.

When the final full export arrives, it replaces `screens/` and this note is updated.
