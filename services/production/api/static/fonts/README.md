# Fonts

Self-hosted. No font service, no CDN: a third-party font would be a row in
`docs/runbooks/data-flow-map.md`, and `tests/unit/api/test_app_skeleton.py`
fails the build on any absolute URL.

These are the same files `plusev.in` serves (Google Fonts, through Next.js
`next/font/google`), so the app and the website render identically.

Each face is split into two files by `unicode-range`, exactly as Google Fonts
splits it, and `scope.css` declares both:

- **latin**: Latin-1, general punctuation and the true minus (U+2212).
- **latin-ext**: everything else Latin, and the currency block that holds the
  rupee sign, ₹ (U+20B9). Without it every rupee figure fell back to a system
  font (TR-013). `tests/unit/api/test_fonts.py` fails if any face loses it.

| File | Family | Weights | Subset |
|---|---|---|---|
| `IBMPlexSans-latin.woff2` | IBM Plex Sans (variable) | 400–600 | latin |
| `IBMPlexSans-latin-ext.woff2` | IBM Plex Sans (variable) | 400–600 | latin-ext |
| `IBMPlexMono-Regular-latin.woff2` | IBM Plex Mono | 400 | latin |
| `IBMPlexMono-Regular-latin-ext.woff2` | IBM Plex Mono | 400 | latin-ext |
| `IBMPlexMono-Medium-latin.woff2` | IBM Plex Mono | 500 | latin |
| `IBMPlexMono-Medium-latin-ext.woff2` | IBM Plex Mono | 500 | latin-ext |
| `IBMPlexMono-SemiBold-latin.woff2` | IBM Plex Mono | 600 | latin |
| `IBMPlexMono-SemiBold-latin-ext.woff2` | IBM Plex Mono | 600 | latin-ext |
| `SourceSerif4-latin.woff2` | Source Serif 4 (variable) | 400–600 | latin |
| `SourceSerif4-latin-ext.woff2` | Source Serif 4 (variable) | 400–600 | latin-ext |

**Where the latin-ext files came from, 30 Oct 2026.** Google Fonts' `css2` API
(IBM Plex Sans v23, IBM Plex Mono v20, Source Serif 4 v15). The same request's
latin files are byte-identical to the latin files already here, so each pair is
one version of one font. Measured with fontTools: every latin-ext file contains
U+20B9 and every latin file does not; every latin file contains U+2212.

**Plex Mono 600, 31 Oct 2026.** Added because the design kit sets the dial's slice
numbers, its centre label and story-card numbers in Mono 600; without the file the
browser would synthesise a bold from 500. Both files from one Google Fonts request
(IBM Plex Mono v20, the version of the 400 and 500 files). fontTools reads each as
IBM Plex Mono SemiBold, weight 600, with U+20B9 in latin-ext only and U+2212 in
latin only.

All ten are under the SIL Open Font License 1.1 (`SourceSerif4-OFL.txt`;
IBM Plex carries the same licence, https://github.com/IBM/plex).
