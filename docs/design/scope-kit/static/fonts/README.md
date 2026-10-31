# Fonts

The kit loads every font from `/static/fonts/` with `@font-face` (see `tokens.css`). No font is fetched from a CDN.
The font files themselves are not in this kit — add them here. All three families are SIL Open Font License 1.1.

| File | Family | Weight | Subset |
|---|---|---|---|
| `IBMPlexSans-Regular-latin.woff2` | IBM Plex Sans | 400 | latin |
| `IBMPlexSans-Regular-latin-ext.woff2` | IBM Plex Sans | 400 | latin-ext |
| `IBMPlexSans-Medium-latin.woff2` | IBM Plex Sans | 500 | latin |
| `IBMPlexSans-Medium-latin-ext.woff2` | IBM Plex Sans | 500 | latin-ext |
| `IBMPlexSans-SemiBold-latin.woff2` | IBM Plex Sans | 600 | latin |
| `IBMPlexSans-SemiBold-latin-ext.woff2` | IBM Plex Sans | 600 | latin-ext |
| `IBMPlexMono-Regular-latin.woff2` | IBM Plex Mono | 400 | latin |
| `IBMPlexMono-Regular-latin-ext.woff2` | IBM Plex Mono | 400 | latin-ext |
| `IBMPlexMono-Medium-latin.woff2` | IBM Plex Mono | 500 | latin |
| `IBMPlexMono-Medium-latin-ext.woff2` | IBM Plex Mono | 500 | latin-ext |
| `IBMPlexMono-SemiBold-latin.woff2` | IBM Plex Mono | 600 | latin |
| `IBMPlexMono-SemiBold-latin-ext.woff2` | IBM Plex Mono | 600 | latin-ext |
| `SourceSerif4-Regular-latin.woff2` | Source Serif 4 | 400 | latin |
| `SourceSerif4-Regular-latin-ext.woff2` | Source Serif 4 | 400 | latin-ext |

Where to get them: the official releases — IBM Plex from github.com/IBM/plex (the `IBM-Plex-Sans` and
`IBM-Plex-Mono` packages ship split WOFF2 files), Source Serif 4 from github.com/adobe-fonts/source-serif.
If a release does not ship latin / latin-ext splits, subset them yourself, e.g.

    pyftsubset IBMPlexSans-Regular.ttf --flavor=woff2 --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+20B9,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD" --output-file=IBMPlexSans-Regular-latin.woff2

The `unicode-range` lines in `tokens.css` match those ranges. The latin range includes U+20B9 (₹) and U+2212 (−),
both used on every rupee figure.
