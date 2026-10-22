# Fonts

Self-hosted. No font service, no CDN: a third-party font would be a row in
`docs/runbooks/data-flow-map.md`, and `tests/unit/api/test_app_skeleton.py`
fails the build on any absolute URL.

These are the same files `plusev.in` serves (Next.js `next/font/google` static
output, latin subset), so the app and the website render identically.

| File | Family | Weights |
|---|---|---|
| `IBMPlexSans-latin.woff2` | IBM Plex Sans (variable) | 400–600 |
| `IBMPlexMono-Regular-latin.woff2` | IBM Plex Mono | 400 |
| `IBMPlexMono-Medium-latin.woff2` | IBM Plex Mono | 500 |
| `SourceSerif4-latin.woff2` | Source Serif 4 (variable) | 400–600 |

All four are under the SIL Open Font License 1.1 (`SourceSerif4-OFL.txt`;
IBM Plex carries the same licence, https://github.com/IBM/plex).
