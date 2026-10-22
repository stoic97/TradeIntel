# Deletion log (append-only — never edit or remove a row)

| Requested | Completed | Trader ID | Deleted | Retained | By |
|---|---|---|---|---|---|
| 2026-10-22 05:25 UTC, through `/account/delete` | 2026-10-22 05:25 UTC | 3 (`stoic97`, the deletion-gate fixture; classified development data; one upload of `demo_tradebook.csv`) | File `924873b4…ab130.enc` from the file store, the trader row and everything derived from it. Confirmed by hand on the droplet: file absent, `select count(*) … where login_id='stoic97'` = 0 | The consent record and this deletion record | Pawan Rathore (founder), with the launch runbook. Backups: weekly schedule; no backup was taken between the upload (05:21 UTC) and the deletion (05:25 UTC), so no backup ever held this data and there was nothing to delete (route 1, trivially). The roll-off sentence therefore rests on DigitalOcean's documented four-weekly-backup retention, not on a backup watched ageing out |
