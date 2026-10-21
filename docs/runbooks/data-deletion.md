# Runbook — Deleting a trader's data

**Two halves, and they are different.** Part A is the app: a trader presses a
button, or an admin runs one command, and code removes everything it can reach.
Part B is everywhere else his file has been — the chat it arrived in, a laptop it
was copied to, the backups. Code cannot reach those, so they are a checklist, and
a checklist is only kept by being worked through every time.

---

# Part A — the app

The trader does it himself at **Account → Delete everything**. He is shown what
goes, what is kept, and what deleting cannot undo, and the page that follows is
his confirmation — there is no email service in v1 (ADR-007), so nothing is sent.

For a request that arrives as a message instead:

```
python -m services.production.api.cli delete-trader --login-id <id> --yes
```

Both paths run the same code and write the same deletion record. What the code
reaches is the database and the encrypted file store; see
`docs/runbooks/data-flow-map.md` for the full list and for what it does not reach.

**A file two accounts uploaded identically is kept** until the last of them is
gone — the store is addressed by the hash of the file's contents, so the blob is
shared. The deletion record says when this happened.

**Backups are not reached by code.** They roll off within 30 days. Note the date
the last backup containing him ages out, and check it on that date.

---

# Part B — everywhere else (Stage 0, manual)

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
| **Derived findings** | Any file recording counts, rates or distributions from his history — these are his data too, and must never be in git | Founder |
| Backups / cloud sync (iCloud, Drive, Time Machine) | Copies of any of the above | Founder |

## Procedure

1. Record the request: date, who asked, how (message screenshot kept **without** the data).
2. Delete the raw file(s) from the raw folder, then from the chat/email where it arrived.
3. Delete every derived artefact for his ID: CTR, features, outputs, notebook cells, inspection reports.
4. Check cloud sync and backups; delete or expire there too.
5. Confirm nothing in the repo references his data (it never should — `.gitignore` blocks it; check anyway: `git log --all -S "<his id>"`).
6. Write one row to `docs/runbooks/deletion-log.md` (append-only): date requested · date completed · trader ID (not name) · what was deleted · what was retained (this log row only) · who did it.
7. Tell him it is done and what was retained (the log row), the same day.

## After both parts

Write one row in `deletion-log.md` covering both halves, and note the date the
last backup holding his data ages out. The row is the only thing retained outside
the app's own deletion record.

## What is retained

Only the deletion-log row. No name, no trades, no derived numbers.
