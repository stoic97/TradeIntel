# Runbook — Deleting a trader's data (Stage 0, manual)

**Why this exists now.** On 4 Oct 2026 recruits were told *"we delete it whenever you say."* That is a promise, and at Stage 0 there is no deletion service, so it is kept by hand, by this checklist, every time. Methodology §15 replaces this with a service at Stage 1.

## Where a trader's data can be

Keep this list current. If data is ever stored somewhere not on this list, add it before doing anything else.

| Location | What | Owner |
|---|---|---|
| Raw tradebook folder (outside the repo) | The file(s) he sent | Founder |
| Derived folder (outside the repo) | CTR, features, any run outputs for him | Engineer |
| Notebooks / scratch | Any analysis that loaded his file | Engineer |
| Chat / email / Telegram / WhatsApp | The message with the attachment | Founder |
| Inspection reports | e.g. `report.txt` from the first inspection | Founder |
| Backups / cloud sync (iCloud, Drive, Time Machine) | Copies of any of the above | Founder |

## Procedure

1. Record the request: date, who asked, how (message screenshot kept **without** the data).
2. Delete the raw file(s) from the raw folder, then from the chat/email where it arrived.
3. Delete every derived artefact for his ID: CTR, features, outputs, notebook cells, inspection reports.
4. Check cloud sync and backups; delete or expire there too.
5. Confirm nothing in the repo references his data (it never should — `.gitignore` blocks it; check anyway: `git log --all -S "<his id>"`).
6. Write one row to `docs/runbooks/deletion-log.md` (append-only): date requested · date completed · trader ID (not name) · what was deleted · what was retained (this log row only) · who did it.
7. Tell him it is done and what was retained (the log row), the same day.

## What is retained

Only the deletion-log row. No name, no trades, no derived numbers.
