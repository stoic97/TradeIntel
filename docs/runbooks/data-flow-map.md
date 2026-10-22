# Data-flow map — every system that touches a tradebook

PRD v1.2 §10, release-gate item 1. **The consent text may name no system that is
not on this list, and this list may contain no system nobody has checked.** If
data is ever stored somewhere not here, add it here before doing anything else.

Status: written 21 Oct 2026, against the code as it stands. Not yet verified on a
running server — that happens with the deployment, and this line changes then.

## What counts as a trader's data

The uploaded file; anything reconstructed from it (fills, trips, open positions,
skipped rows); anything written from those (Journals, their field entries, risk
declarations, dwell events); and the account that ties them together. A count
taken from his history is his data too.

## The systems

| System | What it holds | Encrypted | Retention | Deletion reaches it |
|---|---|---|---|---|
| The droplet's disk — SQLite database | Every table: account, consent, imports, rows, trips, Journals, fields, dwell | No, file permissions only | Until deleted | Yes, `accounts/deletion.py` |
| The droplet's disk — file store | The uploaded file, byte for byte | Yes, Fernet, key in `/etc/scope/`, never in the repo or in backups | Until deleted | Yes, same module |
| Weekly droplet backups (DigitalOcean) | Last week's copy of both of the above | As on disk | Roll off within 30 days: DigitalOcean keeps the four most recent weekly backups | No — by retention, not by code. Checked by the runbook |
| Let's Encrypt | The hostname `scope.plusev.in`. No trader data of any kind | n/a | Theirs | n/a |
| The trader's own browser | A signed session cookie. No trade data | Signed, not encrypted | 30 days, or sign-out | n/a |
| The server's logs | Request paths and status codes. **No request bodies, no uploaded content, no figures** | No | Rotated at 14 days | Nothing of his to delete |

**That is the entire list.** No analytics. No error reporting. No email service.
No CDN: every asset, including HTMX, is served from `static/`. No third-party
font. A test asserts that no rendered page contains an absolute URL, so adding one
breaks the build rather than quietly adding a row to this table.

## Release-gate item 2 — analytics and error reporting receive no trade data

Verified by there being none, which is a stronger statement than a configuration:
there is no analytics client, no error reporter and no outbound HTTP client in the
runtime dependencies. The check is `pyproject.toml` plus the no-absolute-URL test,
not a vendor's documentation.

## Release-gate item 3 — the deletion runbook, executed

`tests/unit/accounts/test_deletion.py::test_the_deletion_drill_the_release_gate_asks_for`
builds a fixture account with data in every location this code can reach, deletes
it, and checks every one afterwards, including the encrypted file on disk. It runs
on every commit.

What that drill does **not** cover, and what a person therefore has to do once on
the real server before the first partner uploads:

1. Delete a fixture account on the server itself, through the page.
2. Confirm the file is gone from the file-store directory on the droplet.
3. Confirm it is gone from the database.
4. Confirm the backup containing it ages out, and record the date it does.
5. Write the row in `deletion-log.md`.

Until step 4 has been seen to happen once, the 30-day sentence in the consent text
is a setting we believe rather than one we have watched work.
