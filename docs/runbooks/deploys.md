# Production deploys — scope.plusev.in

*Newest first. One entry per production deploy, added as the last step of every train
(`deploy.md`, step g). Login ids, passwords and keys never go here: the repository is
public. From the first train on, every deploy is a tag; a sha in "Deployed" means a deploy
that skipped the train.*

Each entry: **Deployed** (tag) · **Previous** · **When** (IST) · **Run by** · **Restore point** ·
**Schema** (alembic revision after) · **Train** (ticket ids) · what happened, if anything did.

---

### 2026-11-06 14:21 IST — configuration only, no code change

- **Deployed:** `7a40e2f` (unchanged) · **Previous:** `7a40e2f`
- **Run by:** founder, over SSH · **Restore point:** none taken (no code or schema change) · **Schema:** 0010
- **What:** a second team admin account. Signed up first, then added to `ADMIN_LOGIN_IDS`, then
  restarted (08:50:05 UTC). `/admin` renders for it.
- **Learned:** an id must be signed up *before* it goes on the admin list. Added first, it silently
  blocks its own sign-up, and the only symptom is "can't sign up or sign in". (Now in `deploy.md` §2.)
- **Open:** there is no password-reset path; one admin account's password is unverified.

### 2026-11-06 14:01 IST — `f496cdd` → `7a40e2f`, admin page enabled

- **Deployed:** `7a40e2f` · **Previous:** `f496cdd`
- **Run by:** founder, over SSH · **Restore point:** not recorded · **Schema:** 0010
- **Train:** #85 (TICKET-852, docs only). No schema or unit change.
- **Found on arrival:** production was already at `f496cdd`, schema 0010, from a deploy between 5 Nov
  20:23 and this one that was never logged. It carried #64 (TICKET-845 layout), #65, #66 (TICKET-848
  admin page), #71–#84, and migration `0010_import_reconstruction_version` (an additive nullable
  column on `import`). Who ran it is not known. This is the deploy the train exists to make
  impossible.
- **What:** `ADMIN_LOGIN_IDS` set in `/etc/scope/scope.env` (the old file kept beside it), after
  checking the account existed. Restarted 08:31:04 UTC, Application startup complete.
- **Smoke:** `/` 200, `/login` 200, `/admin` 404 signed out (correct: the gate answers 404, not 403).
- **Slip:** a placeholder value was written to `ADMIN_LOGIN_IDS` and the service restarted with it
  once (harmless; no such account). Hence "never paste a block with a placeholder in it".

### 2026-11-05 20:23 IST — `ad97504` → `a18d03e`, systemd unit updated

- **Deployed:** `a18d03e` · **Previous:** `ad97504`
- **Run by:** founder, over SSH (Path A plus a unit install) · **Restore point:**
  `/var/backups/scope/scope-20261105T145300Z.db` · **Schema:** 0009 (no migrations)
- **Train:** #55 TICKET-820, #56 TICKET-827, #57 TICKET-823, #59 TICKET-830, #61 TICKET-840,
  #67 TICKET-849, #68 TICKET-842, #69 TICKET-847, #70 TICKET-835. 66 commits, no dependency change.
- **Unit:** `deploy/scope.service` gained `--proxy-headers --forwarded-allow-ips 127.0.0.1` (the
  per-address sign-up cap needs the real address). Copied to `/etc/systemd/system/`, daemon-reload,
  confirmed with `systemctl show -p ExecStart` after the restart.
- **Restart:** Application startup complete 14:53:09 UTC. **Smoke:** `/`, `/login`, `/signup` 200.
- **Side effect, expected:** every session invalidated once (TICKET-849 binds a session to the
  account); every trader signs in again.
- **Rollback:** code only (`git checkout ad97504`, sync, restart); the new unit is harmless under
  old code.

### 2026-11-05 16:41 IST — `ff4e8ce` → `ad97504`, first destructive migration

- **Deployed:** `ad97504` · **Previous:** `ff4e8ce`
- **Run by:** founder, over SSH (stop, then snapshot) · **Restore point:**
  `/var/backups/scope/scope-20261105T111057Z.db` (5.77 MB, integrity_check ok) ·
  **Schema:** 0007 → 0009 (`0008_wtp_asked` new table; `0009_drop_invite_code` drops a table)
- **Train:** #47 TICKET-815, #58 TICKET-826, #60 TICKET-817, #63 TICKET-841 (open sign-up; invite
  gate removed), #53 TICKET-819. 35 commits.
- **What:** service stopped before the backup, so the snapshot is an exact restore point; WAL
  checkpointed; the dropped table's rows exported beside the backup (mode 600). Startup 11:11:05
  UTC, downtime about 15 s. **Smoke:** `/`, `/login`, `/signup` 200.
- **Rollback:** a database restore, not a checkout: `ff4e8ce` expects the dropped table. Sign-ups
  after 11:11 UTC would be lost.
- **Incident:** the block was first pasted on a laptop, not the droplet; `uv sync --no-group
  research` stripped the local research packages (restored with `uv sync --frozen`; the server was
  unaffected). Every deploy block now starts `cd /srv/scope || exit 1`.

### 2026-11-05 14:11 IST — `98687f2` → `ff4e8ce`

- **Deployed:** `ff4e8ce` · **Previous:** `98687f2`
- **Run by:** founder, over SSH · **Restore point:** `/var/backups/scope/scope-20261105T084106Z.db` ·
  **Schema:** 0007 (`0006_report_feedback`, `0007_charges`)
- **Train:** #48 TICKET-816, #49 TICKET-828, #51 TICKET-821, #52 TICKET-832, #62 TICKET-834 (docs),
  and everything merged between #43 and #62. 48 commits; dependencies unchanged.
- **Restart:** Application startup complete 08:41:12 UTC. **Smoke:** `/`, `/login` 200.

### 2026-11-05 00:48 IST — `d4e2014` → `98687f2`

- **Deployed:** `98687f2` · **Previous:** `d4e2014`
- **Run by:** founder, over SSH · **Restore point:** `/var/backups/scope/scope-20261104T191833Z.db`
  (4.6 MB) · **Schema:** 0005 (`trip` gained position, option type, strike, uncapped)
- **Train:** the TICKET-787 epic, the first trader review's fixes, through #43 (TICKET-824). 117
  commits.
- **Restart:** about 3 s, Application startup complete; downtime about 1 s. **Smoke:** `/`, `/login`
  200; the upload page carries "When did you download this file?".
- **Note:** a tester saw "looks the same". That was expected: an existing upload keeps its stored
  reading until it is uploaded again, and the stylesheet may be browser-cached.

---

## Lessons from these runs (folded into `deploy.md`)

- The startup log prints no alembic lines: read the revision with
  `sqlite3 /srv/scope/data/scope.db "select version_num from alembic_version;"`.
  `alembic current` cannot run on its own (its env needs the app's engine).
- An idle SSH session is reset after about 30 minutes: reconnect before pasting, or the block runs
  on your laptop.
- Before any deploy, diff `migrations/versions/` between live and the tag. Any `drop_` or
  `alter_column` means stop before the backup, and rollback is a database restore.
- Diff `deploy/` too: a changed `scope.service` is not applied by checking out code.
- Never paste a block with a placeholder still in it; fill the variable on its first line.
