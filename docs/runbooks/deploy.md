# Runbook — putting Scope on a server, and every deploy after

*v2, 14 November 2026. Sections 1–6 put Scope on a new box, once. **Every deploy after
that is the release train** (below, after Staging): production runs only a tag that a
person has checked on staging, never `main`, and every deploy is logged in
`docs/runbooks/deploys.md`.*

ADR-007 fixes the shape: one DigitalOcean Basic Droplet in Bangalore, under a
product-only account, Caddy and Let's Encrypt in front, systemd behind, weekly
droplet backups (ADR-007, amended 2026-11-16). Everything below follows from that.

**First run: 21 October 2026**, on the cheapest Basic droplet (512 MB, 10 GB) in
BLR1, which is comfortable for a few dozen traders. Everything below has
been done once and the corrections that run produced are folded in. Expect to
correct a line or two anyway, and commit the correction.

## Before you start

- A DigitalOcean account that holds nothing but this product.
- DNS for `scope.plusev.in` pointing at the droplet. Without it, use the
  self-signed block at the bottom of `deploy/Caddyfile` and reach the box by IP.
- Two secrets, generated on the box and never in the repository: the session key
  and the file key.

## 1. The box

Basic droplet, Bangalore (BLR1), Ubuntu LTS. Turn on **backups** when you create
it. The setting, from the droplet's Backups page:

DigitalOcean droplet backups: weekly, the four most recent kept

Read on the console on 16 Nov 2026: weekly on Wednesday, 04:00-08:00 UTC; each image
lives about 27 days, four at a time. An image is of the whole disk, `/etc/scope/`
included, so it holds the keys too: the same vendor, gone within the 30 days the
consent text promises. Scope's own nightly copies are in section 5.

    apt update && apt upgrade -y
    apt install -y git curl ufw sqlite3 s3cmd debian-keyring debian-archive-keyring apt-transport-https
    ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable

`sqlite3` is not optional: `backup.sh` takes the backup with the sqlite CLI's
`.backup`, and without it `cron.daily` fails with "command not found" — a
backup that silently never happens.

`s3cmd` is not optional either: it carries each night's copy off the droplet
(section 5).

If `apt upgrade` asks about `sshd_config`, **keep the version currently
installed**. The image's SSH config is deliberately key-only; the maintainer's
version would replace it, and you would find out on the next reboot.

On a 512 MB droplet, add swap before installing anything. The app does not need
it — it runs in about 100 MB — but the install does, and an OOM-killed
`uv sync` leaves you guessing.

    fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

Caddy, which Ubuntu ships at 2.6.2; the project's own repository is current:

    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" > /etc/apt/sources.list.d/caddy-stable.list
    apt update && apt install -y caddy

Then the user and the directories:

    adduser --system --group --home /srv/scope scope
    mkdir -p /srv/scope/data/files /etc/scope /var/backups/scope
    chown -R scope:scope /srv/scope
    chmod 700 /etc/scope

## 2. The keys

Generate both on the box, into `/etc/scope/scope.env`, mode 0600. The session
key first; the file key after step 3, because it needs the project's own
`cryptography` and a 512 MB box does not want a second Python stack installed
system-wide just to generate one string:

    SCOPE_SECRET_KEY   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
    SCOPE_FILE_KEY     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SCOPE_DB           sqlite:////srv/scope/data/scope.db
    SCOPE_FILES        /srv/scope/data/files
    SCOPE_PRODUCTION   1
    ADMIN_LOGIN_IDS    <login ids, comma-separated, no spaces>

`ADMIN_LOGIN_IDS` names who may open `/admin`. Unset or empty means nobody: the app
still starts and the page is a 404 for everyone. A login id on the list cannot be
taken at sign-up by anyone, because whoever held it would be an admin. So sign up
first, then add the id here and restart: a change takes effect on restart.

A team member's new account is classified the same day, so `/admin` counts traders only:
`.venv/bin/python -m services.production.api.cli --db <SCOPE_DB> classify --login-id <login id> --development-data`.

**Put the file key in the password manager before anything is uploaded.** Lose it
and every stored tradebook is unreadable — Fernet authenticates, so the app
refuses them rather than returning rubbish, which is correct and no comfort.

`SCOPE_PRODUCTION=1` makes the import path refuse an unverified broker file map
(TD-024). That is deliberate: it refuses until someone has checked the Dhan
export against Dhan's own interface.

## 3. The code

    curl -LsSf https://astral.sh/uv/install.sh | sh    # installs to /root/.local/bin
    cp /root/.local/bin/uv /usr/local/bin/uv
    git clone <repo> /srv/scope && cd /srv/scope

uv's interpreter must not live under `/root`. The service runs as `scope`,
`/root` is 0700, and the venv's `python` is a symlink into it — so the service
fails with `203/EXEC` and "Permission denied" on `.venv/bin/python`, which reads
like a problem with the venv rather than with where the interpreter went:

    mkdir -p /opt/uv/python
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv python install 3.11
    chmod -R a+rX /opt/uv
    UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research
    chown -R scope:scope /srv/scope

Now the file key, from the project's own environment:

    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The research group is not installed on the server: it is the Bayesian stack, the
product does not import it, and leaving it out keeps the box small.

## 4. Run it

    cp deploy/scope.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now scope
    systemctl status scope

The market sync's timer (TICKET-998; see "Market data" below). Until Fyers is connected on the
admin page each run records "needs login" and does nothing else:

    cp deploy/scope-market.service deploy/scope-market.timer /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now scope-market.timer
    systemctl list-timers scope-market.timer

Startup takes about five seconds on the smallest droplet — the migration check
and the framework read on one shared vCPU. A `curl` fired straight after a
restart returns 502 with nothing whatever wrong; wait for "Application startup
complete" in `journalctl -u scope`.

    cp deploy/Caddyfile /etc/caddy/Caddyfile
    systemctl reload caddy

Then, as the `scope` user with the environment loaded. `/etc/scope` is 0700 and
root-owned, so root reads the file and passes it in:

    sudo -u scope env $(grep -v '^#' /etc/scope/scope.env | xargs) \
        .venv/bin/python -m services.production.api.cli init-db

Sign-up is open at the site's front door, so there is nothing to mint.

## 5. Backups and the drill

Three copies exist besides the live data, and each is gone within the 30 days the
consent text promises:

- DigitalOcean droplet backups: weekly, the four most recent kept
- Scope's own nightly copies: 29 days on the droplet and in Spaces (BLR1); the Spaces lifecycle rule deletes at 30

`deploy/backup.sh` makes the nightly copy in `/var/backups/scope`, encrypts the
database copy with the file key (the stored files are encrypted already), and uploads
both to a Spaces bucket in BLR1 under this product's account. The key is never
uploaded. Everything in `/var/backups/scope` goes once it is 29 days old, restore points
and stray copies included, and the bucket's copies go by the same clock; the bucket's
lifecycle rule is the backstop. Without the bucket's config the script
still makes the local copy, then exits non-zero.

Once, as root on the droplet. Create the bucket first (Spaces, BLR1, this account,
private) and a Spaces access key for it, then fill the `BUCKET=` line and paste:

    cd /srv/scope || exit 1
    BUCKET=
    apt install -y s3cmd
    s3cmd --configure -c /etc/scope/s3cfg
    chmod 600 /etc/scope/s3cfg
    printf 'SCOPE_SPACES=s3://%s/scope\n' "$BUCKET" > /etc/scope/spaces.env && chmod 600 /etc/scope/spaces.env
    s3cmd -c /etc/scope/s3cfg expire "s3://$BUCKET" --expiry-days=30 --expiry-prefix=scope/
    s3cmd -c /etc/scope/s3cfg getlifecycle "s3://$BUCKET"
    cp deploy/backup.sh /etc/cron.daily/scope-backup && chmod 755 /etc/cron.daily/scope-backup
    /etc/cron.daily/scope-backup
    s3cmd -c /etc/scope/s3cfg ls "s3://$BUCKET/scope/"

`s3cmd --configure` asks for the access key and secret; give `blr1.digitaloceanspaces.com`
as the endpoint and `%(bucket)s.blr1.digitaloceanspaces.com` as the bucket template, no
encryption password, HTTPS yes. Expected: `getlifecycle` shows `<Prefix>scope/</Prefix>` and `<Days>30</Days>` (the rule covers the
trader copies only; the market bars under `market/` are kept); the
backup prints "backed up to" and then "copied off the droplet"; `ls` lists
`scope-<stamp>.db.enc` and `files-<stamp>.tar.gz`. `cron.daily` runs the installed copy,
not the checkout, so every deploy re-installs a changed `backup.sh` (the release train,
step d).

Run `deploy/restore-drill.sh` by hand the first time, then monthly, alternating with
`--from-spaces`, which restores the newest copy in the bucket. It restores into `/tmp`
and decrypts one stored file with the live key — the part a database-only check
misses. It reads the key from the environment:

    cd /srv/scope || exit 1
    set -a; . /etc/scope/scope.env; set +a
    deploy/restore-drill.sh --from-spaces

## Staging

A second Scope on the same droplet, so a person can check a change before a trader
sees it: `https://staging.scope.plusev.in`, behind a browser password (founder's
password manager), on port 8001, in `/srv/scope-staging`, with its own database and
session key. It runs `main`, or any commit `main` already holds; production runs only a
tag.

Refresh it by hand, as root, right before testing — never on a timer:

    /srv/scope-staging/deploy/refresh-staging.sh
    /srv/scope-staging/deploy/refresh-staging.sh 09919b5

With no argument it takes `origin/main`. With one argument it takes that tag or sha
instead, which is how a train whose tag sits behind `main` is checked (TICKET-1003). A
ref that does not resolve, or that `origin/main` does not hold, is refused before the
service stops, and staging keeps running what it was running. To judge a ref and change
nothing, put `REFRESH_STAGING_CHECK_ONLY=1` before the command.

It restores the newest backup from `/var/backups/scope` into staging, checks out the ref
it was given, starts `scope-staging`, and prints the version it runs and whether that
version was `main`. Migrations
newer than production apply at startup, as they do in production. First install is
the numbered block at the top of the script. Staging is never backed up; it is
rebuilt from production's backups on every refresh. `deploy/scope-staging.service`
can write only `/srv/scope-staging/data`.

## The release train — every deploy after the first

Seven steps, in this order, each by the person named. A block is pasted whole, after its
placeholder line (`TAG=`, `SHA=`, `PREV=`, `RP=`, right under the `cd`) is filled with
the real value; never paste one with an example value still in it. An SSH session idle for half an
hour is reset: reconnect before pasting, or the block runs on your laptop.

| Step | Who | Where |
|---|---|---|
| a. Refresh staging | the tester | droplet, root |
| b. UAT on staging | the tester (never the author of a ticket they check) | browser |
| c. Tag | **the founder only**, after a Pass is recorded | laptop |
| d. Deploy the tag | founder (or whoever the founder names) | droplet, root |
| e. Check production | same person | droplet and browser |
| f. Log it | same person | `docs/runbooks/deploys.md` |
| g. Tell the traders | customer team | the loop tracker |

### a. Refresh staging at the sha the train will tag

    /srv/scope-staging/deploy/refresh-staging.sh

Expected, last lines:

    ==> 9/9 check /health through Caddy
    without the password: 401, as it must be
    from the app on :8001: {"status":"ok","code_version":"3f2a1bc"}

    Staging is refreshed and running 3f2a1bc (origin/main).

That sha is **what will be tagged**. Write it at the top of the train page. If the script
stops, it names the step; fix that before anyone tests.

A train split into two tags does not start at `main`. Give the script the first tag's
sha, and staging runs that commit and nothing newer (TICKET-1003):

    /srv/scope-staging/deploy/refresh-staging.sh 09919b5

The last line then reads `Staging is refreshed and running 09919b5 (ref 09919b5, not
main)`, and that sha is what step c tags. The ref must be a commit `origin/main` already
holds; anything else is refused before the service stops. The second tag gets its own
refresh, at its own sha, once the first train is live.

The ref is a tag or a sha (7 to 40 lower-case hex characters). `main`, `HEAD` and
`origin/main~3` are refused before the service stops, because a branch name moves.

A ref older than the script has no script in its tree, and step 4 rewrites the checkout
the script lives in. So before the first such refresh, copy the script outside the
checkout and run that copy, and run it again for the refresh back to `main`:

    install -m 755 /srv/scope-staging/deploy/refresh-staging.sh /usr/local/sbin/refresh-staging
    /usr/local/sbin/refresh-staging 09919b5

After the train is tagged, `/usr/local/sbin/refresh-staging` with no argument takes
`origin/main` again. Install the copy afresh whenever `deploy/refresh-staging.sh` changes.

### b. UAT on staging

The tester works through every ticket on the train against its gate, then the fixed pass
in `docs/runbooks/uat-smoke.md` on a phone and a laptop. Results go in the loop tracker
(feedback-loop repo: `tracker/record_verify.py`, Verify result Pass / Fail / Can't
check), on the train page (`trains/<date>.md`), and as a `uat-pass` / `uat-fail` label on
each Jira ticket. The tester's page there, `onboarding/tester.md`, is the whole station.

**A train's results, in one query.** The deployer reads them in Jira, not ticket by ticket:

    project = TICKET AND labels in (uat-pass, uat-fail) AND key in (<the train's tickets>)

A ticket the query doesn't return has no result yet, and the train is not tagged.
`labels = needs-yes` lists the drafted gates held for the founder's yes. Jira makes a label
the first time it is used, so there is nothing to set up: the first tester's Pass is what
creates `uat-pass` (ruled 21 Nov 2026, TICKET-1014). Never add `uat-pass` to test the
label: a Pass is recorded only by a tester who saw the gate true on staging.

Nothing is tagged until every ticket on the train has a result and the smoke pass is a
Pass on both devices. A Fail does not stop the train if the founder takes that ticket off
it: its fix rides the next train.

### c. Tag the sha that passed (founder only)

On the founder's laptop, in a clean clone. Tag the sha staging ran in step a, not
whatever `main` is now: `main` may have moved since the test.

    SHA=3f2a1bc; TAG=v2026.11.14; MSG="train: TICKET-..., TICKET-..."
    git fetch --quiet origin
    git merge-base --is-ancestor "$SHA" origin/main && echo "on main"
    git tag -a "$TAG" -m "$MSG" "$SHA"
    git push origin "$TAG"

Expected: `on main`, then `* [new tag]  v2026.11.14 -> v2026.11.14`. A second train the
same day is `v2026.11.14.2`. Tags are annotated and are never moved or deleted once
pushed; a wrong tag is fixed by a new one.

### d. Deploy the tag

Every block is one `( ... )` that starts with `cd /srv/scope`, so pasted in the wrong window
it prints `STOP: not on the server` and does nothing. After each step that matters there is a
`STOP: <why>` line: the block ends there, your shell stays open, and a clean run ends in
`DONE <name>`. Fix what the line says and paste the same block again; after `systemctl stop`
(Path B and its rollback) the line also says the service is DOWN, and the block is not pasted
again until you have decided between restarting it and rolling back. First, where production is
and what the tag changes:

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      TAG=v2026.11.14
      stop() { echo "STOP: $1"; exit 1; }
      DIRTY=$(git status --short) || stop "git status failed"
      test -z "$DIRTY" || { echo "$DIRTY"; stop "the box has changes made by hand; find out who before going on"; }
      git fetch --quiet --tags origin || stop "git fetch failed; nothing was compared"
      git merge-base --is-ancestor "$TAG^{commit}" origin/main || stop "$TAG is not on origin/main; do not deploy it"
      LIVE=$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD) || stop "cannot tell what is live"; echo "live: $LIVE"
      git diff --stat "$LIVE" "$TAG" -- migrations/versions deploy/ || stop "git diff failed"
      { git show "$TAG":deploy/classify_release.py > /tmp/classify_release.py 2>/dev/null && echo "classifier: from $TAG"; } || { git show origin/main:deploy/classify_release.py > /tmp/classify_release.py && echo "classifier: from origin/main ($TAG predates it)"; } || stop "CHECK DID NOT RUN - classify by hand"
      python3 /tmp/classify_release.py "$LIVE" "$TAG"
      case $? in
        0) echo "PATH A - additive or no migration" ;;
        1) echo "PATH B - destructive: stop the service BEFORE the snapshot, rollback is a DB restore" ;;
        2) echo "READ BY HAND - Path B applies unless a person has read these migrations and says otherwise" ;;
        *) stop "CHECK DID NOT RUN - classify by hand, do not assume Path A" ;;
      esac
      echo "DONE where"
    )

Expected: `git status --short` prints **nothing**. Any line there means someone changed
the box by hand: the block stops, so find out who before going on. It also refuses a tag that
is not on `origin/main`. `live:` is the previous tag (a
sha only on the first train, or after a deploy that skipped the train).

Before either path, check that no new migration sits behind the live tag's head. Like every
block here it is one `( ... )` with its own `TAG`: set it to the same tag as the block above.
It stops if `TAG` or `LIVE` comes out empty rather than checking nothing.

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      set -u
      TAG=v2026.11.14
      stop() { echo "STOP: $1"; exit 1; }
      [ -n "$TAG" ] || { echo "STOP: TAG is not set (set it to the tag in the block above)"; exit 1; }
      LIVE=$(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD) || stop "cannot tell what is live"
      [ -n "$LIVE" ] || { echo "STOP: LIVE is not set (cannot tell what is live)"; exit 1; }
      rev_of() { git show "$1" | grep -E "^revision = " | sed "s/.*['\"]\([^'\"]*\)['\"].*/\1/"; }
      down_of() { git show "$1" | grep -E "^down_revision = " | grep -v "= None" | sed "s/.*['\"]\([^'\"]*\)['\"].*/\1/"; }
      revs=" "; downs=" "
      for f in $(git ls-tree --name-only "$LIVE" migrations/versions/ | grep -E '/[0-9]{4}_[^/]*\.py$'); do
        revs="$revs$(rev_of "$LIVE:$f") "; downs="$downs$(down_of "$LIVE:$f") "
      done
      heads=""
      for r in $revs; do case "$downs" in *" $r "*) ;; *) heads="$heads $r" ;; esac; done
      set -- $heads
      [ $# -eq 1 ] || stop "the live tag has $# migration heads ($heads ); expected one"
      head=$1
      echo "live head: $head (the revision no other migration revises)"
      new=$(git diff --name-only --diff-filter=A "$LIVE" "$TAG" -- migrations/versions) || stop "git diff failed; nothing was checked"
      while [ -n "$new" ]; do
        next=""
        for f in $new; do [ "$(down_of "$TAG:$f")" = "$head" ] && { [ -z "$next" ] || stop "$next and $f both revise $head: two heads"; next=$f; }; done
        [ -n "$next" ] || stop "no new migration revises $head; these do not continue the live head:$(printf ' %s' $new)"
        rev=$(rev_of "$TAG:$next")
        case "$revs" in *" $rev "*) stop "$next reuses revision $rev, which the live chain already has" ;; esac
        echo "ok: $next ($rev) revises $head"
        revs="$revs$rev "; head=$rev
        new=$(printf '%s\n' $new | grep -vxF "$next" || true)
      done
      echo "DONE migration heads"
    )

Expected: the first new migration's `down_revision` is the live head, each later one's is the
one before it: `live head:` names one revision, an `ok:` line follows for each new migration, then
`DONE migration heads`. The live head is read from the chain (the revision no other migration
revises), never from the highest number: main's chain runs 0019 → 0022 → 0020 → 0021, so its head
is 0021. Each new migration must revise the head before it, and no new `revision` may already be
in the live chain. Any `STOP:` line: stop, and do not deploy the tag. Why: a migration whose revision id the live database already
counts as applied is skipped with no error, so its table never exists and the page that reads
it fails; a `down_revision` behind the live head leaves two heads, and the app refuses to start
(`alembic upgrade head` needs one). Fix it on `main` with a new tag; never edit a migration a
tag has shipped.

The first block's last line before `DONE where` decides the path: `PATH A` -> **Path A**; `PATH B` -> **Path B**; `READ BY HAND` -> a
person reads those migrations and rules, and **Path B** applies until they do;
`CHECK DID NOT RUN` is never Path A. A tag older than `deploy/classify_release.py` (train 1's) is classified with the copy on `origin/main`, and the block says so (`classifier: from origin/main`): the classifier only reads the migrations between `$LIVE` and `$TAG`, so a newer copy judges an older range the same way. A tag older than the market units skips them (`<unit>: not in <tag>, skipped`) instead of stopping after the checkout. The check reads only the `upgrade()` body of every
migration added or changed between `$LIVE` and `$TAG`: a drop that runs only on a
rollback (in `downgrade()`) does not make a release destructive, and `batch.drop_column`
counts the same as `op.drop_column`.

Production then sits on a detached HEAD at the tag. That is correct, and `git status
--short` still reports local changes, so the guard above still works. Do not "fix" it
with `git switch main`.

**Path A** (no migration, or only additive ones). Back up the live database, then deploy:

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      TAG=v2026.11.14
      stop() { echo "STOP: $1"; exit 1; }
      RP=/var/backups/scope/scope-$(date -u +%Y%m%dT%H%M%SZ).db
      sqlite3 /srv/scope/data/scope.db ".backup '$RP'" && chmod 600 "$RP" && echo "restore point: $RP" || stop "the backup failed"
      git checkout --quiet "$TAG" || stop "git checkout $TAG failed; the service was not restarted"
      UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research || stop "uv sync failed"
      cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; } || stop "scope.service was not installed"
      for u in scope-market.service scope-market.timer; do [ -f deploy/$u ] || { echo "$u: not in $TAG, skipped"; continue; }; cmp -s deploy/$u /etc/systemd/system/$u || { cp deploy/$u /etc/systemd/system/ && systemctl daemon-reload && echo "$u updated"; } || stop "$u was not installed"; done
      cmp -s deploy/backup.sh /etc/cron.daily/scope-backup || { cp deploy/backup.sh /etc/cron.daily/scope-backup && chmod 755 /etc/cron.daily/scope-backup && echo "backup script updated"; } || stop "the backup script was not installed"
      chown -R scope:scope /srv/scope || stop "chown failed"
      systemctl restart scope || stop "systemctl restart scope failed"
      echo "DONE path-a"
    )

**Path B** (a migration drops or alters something). Stop first, so the snapshot is an
exact restore point; rollback for this release is that snapshot, not a checkout:

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      TAG=v2026.11.14
      stop() { echo "STOP: $1"; exit 1; }
      systemctl stop scope || stop "systemctl stop scope failed; check systemctl status scope"
      stop() { echo "STOP: $1; the service is DOWN, restart it or roll back"; exit 1; }
      sqlite3 /srv/scope/data/scope.db "PRAGMA wal_checkpoint(TRUNCATE);" || stop "wal_checkpoint failed"
      RP=/var/backups/scope/scope-$(date -u +%Y%m%dT%H%M%SZ).db
      sqlite3 /srv/scope/data/scope.db ".backup '$RP'" && chmod 600 "$RP" && echo "restore point: $RP" || stop "the backup failed"
      test "$(sqlite3 "$RP" "PRAGMA integrity_check;")" = ok || stop "integrity_check on $RP was not ok, never restore from it"; echo "integrity_check: ok"
      git checkout --quiet "$TAG" || stop "git checkout $TAG failed"
      UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research || stop "uv sync failed"
      cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; } || stop "scope.service was not installed"
      for u in scope-market.service scope-market.timer; do [ -f deploy/$u ] || { echo "$u: not in $TAG, skipped"; continue; }; cmp -s deploy/$u /etc/systemd/system/$u || { cp deploy/$u /etc/systemd/system/ && systemctl daemon-reload && echo "$u updated"; } || stop "$u was not installed"; done
      cmp -s deploy/backup.sh /etc/cron.daily/scope-backup || { cp deploy/backup.sh /etc/cron.daily/scope-backup && chmod 755 /etc/cron.daily/scope-backup && echo "backup script updated"; } || stop "the backup script was not installed"
      chown -R scope:scope /srv/scope || stop "chown failed"
      systemctl start scope || stop "systemctl start scope failed"
      echo "DONE path-b"
    )

Expected (Path B): `integrity_check: ok`. If the block stops there instead, `systemctl start scope`
on the old code (`git checkout` the `live:` tag from the first block first if you already moved)
and stop the train.

Either path: a changed `scope.service`, market unit or `backup.sh` is not applied by checking
out code (`cron.daily` runs its own copy). The `cmp` lines install each only when it differs,
and say `unit updated`, `scope-market.timer updated` or `backup script updated` when they did.
The timer picks up a changed service on its next run; nothing needs restarting for it.

### e. Check production

Startup takes about five seconds; a `curl` straight after the restart can answer 502
with nothing wrong.

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      stop() { echo "STOP: $1"; exit 1; }
      LOG=$(journalctl -u scope --since "-3 min" --no-pager) || stop "journalctl failed"
      echo "$LOG" | grep -E "Application startup complete|Traceback"
      echo "$LOG" | grep -q "Application startup complete" || stop "no startup line yet; wait ten seconds and paste this block again"
      echo "$LOG" | grep -q "Traceback" && stop "a Traceback in the log; read it before anything else"
      sqlite3 /srv/scope/data/scope.db "select version_num from alembic_version;" || stop "cannot read the alembic revision"
      ls migrations/versions | sort | tail -1
      curl -s https://scope.plusev.in/health || stop "curl /health failed"; echo
      curl -s -o /dev/null -w '%{http_code}\n' https://scope.plusev.in/login || stop "curl /login failed"
      echo "DONE check"
    )

Expected: `Application startup complete` and no `Traceback`. The alembic revision matches
the newest migration file (the startup log prints no alembic lines, and `alembic current`
cannot run on its own). `/health` says `"code_version":"v2026.11.14"`, **the tag**: a sha
there means the checkout did not land on the tag. `/login` answers `200`.

### f. Log it

Add the entry at the top of `docs/runbooks/deploys.md`, in the shape the entries there
use: tag, previous tag, time IST, who ran it, the restore point printed in step d, the
alembic revision from step e, the train's ticket ids. Open it as a one-file PR titled
`deploy: v2026.11.14`. No login ids, passwords or keys in it; the repository is public.

### g. Close the loop

Every ticket on the train that passed is now live. The tracker shows those rows at
*6b Verified*; the customer team tells each trader who raised one, as the loop says.

### Rollback

The previous tag is the second line of:

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      stop() { echo "STOP: $1"; exit 1; }
      git tag --sort=-creatordate | head -2; test "${PIPESTATUS[0]}" = 0 || stop "git tag failed"
      echo "DONE tags"
    )

**After Path A** (code only):

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      PREV=v2026.11.07
      stop() { echo "STOP: $1"; exit 1; }
      git checkout --quiet "$PREV" || stop "git checkout $PREV failed; the service was not restarted"
      UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research || stop "uv sync failed"
      cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; } || stop "scope.service was not installed"
      cmp -s deploy/backup.sh /etc/cron.daily/scope-backup || { cp deploy/backup.sh /etc/cron.daily/scope-backup && chmod 755 /etc/cron.daily/scope-backup && echo "backup script updated"; } || stop "the backup script was not installed"
      chown -R scope:scope /srv/scope || stop "chown failed"
      systemctl restart scope || stop "systemctl restart scope failed"
      echo "DONE rollback-a"
    )

An additive migration stays applied; older code ignores the new column or table.

**After Path B** (database restore): the older code expects what the migration removed,
so the restore point goes back with it. Anything written after the snapshot (sign-ups,
uploads) is lost; say so in the log.

    ( cd /srv/scope || { echo "STOP: not on the server"; exit 1; }
      PREV=v2026.11.07; RP=/var/backups/scope/scope-20261114T093000Z.db
      stop() { echo "STOP: $1"; exit 1; }
      systemctl stop scope || stop "systemctl stop scope failed; check systemctl status scope"
      stop() { echo "STOP: $1; the service is DOWN, restart it or roll back"; exit 1; }
      cp "$RP" /srv/scope/data/scope.db && rm -f /srv/scope/data/scope.db-wal /srv/scope/data/scope.db-shm || stop "the restore point could not be copied back and the live database may be half written: copy $RP over it by hand first"
      git checkout --quiet "$PREV" || stop "git checkout $PREV failed"
      UV_PYTHON_INSTALL_DIR=/opt/uv/python uv sync --frozen --no-group research || stop "uv sync failed"
      cmp -s deploy/scope.service /etc/systemd/system/scope.service || { cp deploy/scope.service /etc/systemd/system/ && systemctl daemon-reload && echo "unit updated"; } || stop "scope.service was not installed"
      cmp -s deploy/backup.sh /etc/cron.daily/scope-backup || { cp deploy/backup.sh /etc/cron.daily/scope-backup && chmod 755 /etc/cron.daily/scope-backup && echo "backup script updated"; } || stop "the backup script was not installed"
      chown -R scope:scope /srv/scope || stop "chown failed"
      systemctl start scope || stop "systemctl start scope failed"
      echo "DONE rollback-b"
    )

Then step e, and a log entry for the rollback.

### Hotfixes

A bug on the 24-hour clock does not wait for the train, and does not skip staging. Its PR
merges to `main`; staging is refreshed (step a); the author **and one other person** check
it there the same day; the founder tags that sha with the day's next number
(`v2026.11.14.2`) and it deploys by step d like any train, logged by step f. No path
deploys `main` directly.

### When `deploy/Caddyfile` changes

Caddy serves production as well as staging, so its config is installed by a person, on its
own, never by `refresh-staging.sh`. Do it before the deploy window of the
train that carries the change, while production still runs the previous train: a bad file is
then found with nothing else moving. Before a train is tagged, check whether it touches the
file (`git log --oneline <last tag>..$SHA -- deploy/Caddyfile`); if it does, this comes first.

The staging block reads its user and bcrypt hash from `/etc/caddy/staging-auth.env`, which
systemd hands Caddy through `caddy.service.d/staging-auth.conf`. A plain `caddy validate` in
a root shell has neither, so it checks a different config from the one the reload loads. Load
the file first, as below. bash's `.` expands `$` and a bcrypt hash is full of them
(`$2a$14$…`), so the hash must sit in single quotes in that file (`SCOPE_STAGING_HASH='…'`);
systemd strips the quotes and reads the same value, and the block refuses anything but one
line for it, quoted and with the closing quote. If
the file or the drop-in is missing, do staging's first install (the header of
`deploy/refresh-staging.sh`) before this.

Fill `SHA=` in every block. Each block is one `( ... )`: when it stops, it prints one `STOP:`
line saying why and the rest of that block does not run, in a login shell or a shell inside one,
and your shell stays open. Fix what the line says and paste the same block again.

    ( cd /srv/scope || { echo "STOP: no /srv/scope here; is this the droplet?"; exit 1; }
      SHA=
      stop() { echo "STOP: $1"; exit 1; }
      test -n "$SHA" || stop "SHA= is empty; fill it in"
      curl -s -o /dev/null -w "production before: %{http_code}\n" https://scope.plusev.in/health
      git fetch --quiet origin || stop "git fetch failed"
      git show "$SHA:deploy/Caddyfile" > /tmp/Caddyfile.next || stop "git show failed: no deploy/Caddyfile at $SHA"
      test -s /tmp/Caddyfile.next || stop "the file fetched at $SHA is empty"
      cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-$SHA" || stop "the live file could not be saved"
      test -f /etc/caddy/staging-auth.env && test -f /etc/systemd/system/caddy.service.d/staging-auth.conf || stop "staging auth is missing; do staging's first install"
      echo "staging auth: present"
      test "$(grep -c SCOPE_STAGING_HASH /etc/caddy/staging-auth.env)" = 1 || stop "staging-auth.env must hold SCOPE_STAGING_HASH on exactly one line"
      grep -qx "SCOPE_STAGING_HASH='[^'][^']*'" /etc/caddy/staging-auth.env || stop "the SCOPE_STAGING_HASH line must be single-quoted, closing quote included"
      ( set -a; . /etc/caddy/staging-auth.env; set +a; caddy validate --config /tmp/Caddyfile.next --adapter caddyfile ) || stop "caddy refused /tmp/Caddyfile.next; nothing was installed"
      echo "VALID"
    )

Go on only after `staging auth: present` and `VALID`. The next block validates the same file
again right before it replaces the live one. A stop before the install leaves the live file as
it was; after it, the block puts the saved copy back, and its line says whether that worked:

    ( cd /srv/scope || { echo "STOP: no /srv/scope here; is this the droplet?"; exit 1; }
      SHA=
      stop() { echo "STOP: $1"; exit 1; }
      test -n "$SHA" || stop "SHA= is empty; fill it in"
      undo() { cp "/etc/caddy/Caddyfile.before-$SHA" /etc/caddy/Caddyfile && stop "$1; the saved copy is back"; stop "$1, and the saved copy could NOT be put back: copy it by hand"; }
      test -s /tmp/Caddyfile.next || stop "/tmp/Caddyfile.next is empty or missing; nothing was installed, run the first block again"
      git show "$SHA:deploy/Caddyfile" | diff - /tmp/Caddyfile.next > /dev/null || stop "/tmp/Caddyfile.next is not the file at $SHA; nothing was installed"
      test -s "/etc/caddy/Caddyfile.before-$SHA" || stop "no saved copy for $SHA; nothing was installed, run the first block again"
      ( set -a; . /etc/caddy/staging-auth.env; set +a; caddy validate --config /tmp/Caddyfile.next --adapter caddyfile ) || stop "caddy refused /tmp/Caddyfile.next; nothing was installed"
      install -m 644 /tmp/Caddyfile.next /etc/caddy/Caddyfile || undo "the install failed"
      diff /tmp/Caddyfile.next /etc/caddy/Caddyfile > /dev/null || undo "the live file is not the file at $SHA"
      echo "matches $SHA"
      ( set -a; . /etc/caddy/staging-auth.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile ) && systemctl reload caddy || undo "caddy refused the installed file or its reload"
      sleep 2
      curl -s -o /dev/null -w "production after: %{http_code}\n" https://scope.plusev.in/health
      curl -s -o /dev/null -w "staging without the password: %{http_code}\n" https://staging.scope.plusev.in/health
    )

Expected: `matches <sha>`, `production after:` the same as `production before:` (200), and
staging without the password `401`, so the staging block and its `basic_auth` survived. If
production answers anything else, put the old file back at once:

    ( cd /srv/scope || { echo "STOP: no /srv/scope here; is this the droplet?"; exit 1; }
      SHA=
      stop() { echo "STOP: $1"; exit 1; }
      test -n "$SHA" || stop "SHA= is empty; fill it in"
      test -s "/etc/caddy/Caddyfile.before-$SHA" || stop "no saved copy for $SHA"
      cp "/etc/caddy/Caddyfile.before-$SHA" /etc/caddy/Caddyfile || stop "the saved copy could not be put back"
      systemctl reload caddy || stop "the saved copy is back but caddy did not reload"
    )

Log it at the top of `docs/runbooks/deploys.md`: the time, who did it, the sha, and the
before and after codes.

## Market data (TICKET-998)

Bars for the bar-based figures live in `/srv/scope/data/market`, one gzip file per trading day
(the layout and the day writer are in `docs/runbooks/price-series.md`). The sync keeps them
current; nobody's laptop does.

**The founder's steps, once:**

1. Add the Fyers app's keys to `/etc/scope/scope.env` (root-owned, 0600; never in the
   repository): `FYERS_APP_ID`, `FYERS_SECRET_KEY`, and `FYERS_REDIRECT_URI`, the address the app
   is registered with in the Fyers dashboard. Then `systemctl restart scope`.
2. For one click, register an app whose redirect is `https://scope.plusev.in/admin/fyers/callback`
   (a second app in the Fyers dashboard, or the existing one's redirect changed) and use its keys
   above. With the existing app, whose redirect lands on google.com, it still works: the card
   says to paste the address bar.
3. Seed the series from the laptop that holds them, as `docs/runbooks/price-series.md` says
   (split with `scripts/split_series_by_day.py`, then `scp -r` the folder up).
4. Each morning after 06:00, open `/admin`, **Market data**, and Connect Fyers. The day's login
   ends at 06:00 the next day.

**What runs:** `scope-market.timer` starts `scope-market.service` every ten minutes and at 00:15
IST. Each run adds every finished session after the last day held (never today's), fetches the
stock days traders asked for, records the run, and exits, at nice 10, half a CPU and 200 MB at
most. `journalctl -u scope-market` shows counts, dates and reasons only. The card on `/admin` shows
the last day held per series, days behind, the last run, the stock days waiting, and the login.

**Staging** gets no Fyers keys: its card says "not set up on this server", it never syncs, and it
reads production's folder read only (`SCOPE_MARKET_DIR` in `deploy/staging.env.example`). Don't
install the market units for staging.

### Train 3, once: market data before the restart

Train 3 is the first deploy that needs more than a checkout and a restart. Paste these blocks
as root, one at a time and in this order, after step c has a tag and before step d's Path A or
Path B restarts production. Each block runs in a subshell that stops at the first failing line
and prints `STOPPED`; when it does, fix that and paste the same block again before going on.
No block holds a key's value, and none reads an env file with `.` or `source`: a `$` inside a
value would be expanded (the lesson of the caddy install).

**1. Staging first.** Staging holds no Fyers keys and reads production's market folder read
only. Check that before production changes:

    cd /srv/scope || exit 1
    ( set -eu
      grep -qx 'SCOPE_MARKET_DIR=/srv/scope/data/market' /etc/scope/staging.env || { echo "STOP: staging.env has no SCOPE_MARKET_DIR (deploy/staging.env.example)"; exit 1; }
      if grep -qE '^FYERS_' /etc/scope/staging.env; then echo "STOP: staging must hold no Fyers keys"; exit 1; fi
      echo "staging: reads the market folder read only, holds no keys"
    ) || echo "STOPPED: fix the line above before going on"

Then open a market page on staging: before the folder below exists it shows its no-data state
and no error (TICKET-1077, line 4).

**2. The three Fyers settings.** This block adds each name with a placeholder, never a value:

    cd /srv/scope || exit 1
    ( set -eu
      for k in FYERS_APP_ID FYERS_SECRET_KEY FYERS_REDIRECT_URI; do
        grep -qE "^$k=" /etc/scope/scope.env || printf '%s=<%s>\n' "$k" "$k" >> /etc/scope/scope.env
      done
      chown root:root /etc/scope/scope.env && chmod 600 /etc/scope/scope.env
      grep -cE '^FYERS_' /etc/scope/scope.env
    ) || echo "STOPPED: fix the line above before going on"

Now open `/etc/scope/scope.env` in an editor (`nano /etc/scope/scope.env`) and replace each
`<...>` with the value from the Fyers dashboard. Type the values into the editor, never into the
shell, so none lands in its history. Then check, without printing a value:

    cd /srv/scope || exit 1
    ( set -eu
      for k in FYERS_APP_ID FYERS_SECRET_KEY FYERS_REDIRECT_URI; do
        line=$(grep -E "^$k=" /etc/scope/scope.env) || { echo "STOP: $k missing"; exit 1; }
        case "${line#*=}" in ''|'<'*) echo "STOP: $k still a placeholder"; exit 1;; esac
        echo "$k set"
      done
      [ "$(stat -c '%U %a' /etc/scope/scope.env)" = "root 600" ] || { echo "STOP: scope.env must be root, 600"; exit 1; }
    ) || echo "STOPPED: fix the line above before going on"

**3. The bucket's lifecycle rule, scoped to `scope/`.** The market bars get one copy off the
droplet, in the same Spaces bucket the nightly backups use, under the `market/` prefix beside
`scope/` (ruling of 24 Nov). Fyers serves bars by contract, and an expired contract is an invalid
symbol to it (`services/shared/market/fyers_history.py`), so once a day is lost on the droplet,
Scope cannot fetch it again. The 30-day rule set in section 5 covers the whole bucket; it must
cover only `scope/`, where every trader copy lives, or it would delete the market copies too:

    cd /srv/scope || exit 1
    ( set -eu
      SPACES=$(grep -E '^SCOPE_SPACES=' /etc/scope/spaces.env | cut -d= -f2-)
      BUCKET=${SPACES%/scope}
      [ -n "$SPACES" ] && [ "$BUCKET" != "$SPACES" ] || { echo "STOP: SCOPE_SPACES must end in /scope"; exit 1; }
      s3cmd -c /etc/scope/s3cfg expire "$BUCKET" --expiry-days=30 --expiry-prefix=scope/
      s3cmd -c /etc/scope/s3cfg getlifecycle "$BUCKET"
    ) || echo "STOPPED: fix the line above before going on"

Expected: `getlifecycle` shows `<Prefix>scope/</Prefix>` and `<Days>30</Days>`. Without the
`<Prefix>` line the rule still covers the whole bucket: stop the train, because the first
market copy would expire at 30 days. The trader copies keep their 30 days either way.

**4. The market folder**, owned by the app's user. Seed it afterwards as `docs/runbooks/price-series.md` says:

    cd /srv/scope || exit 1
    ( set -eu
      install -d -o scope -g scope -m 0750 /srv/scope/data/market
      stat -c '%U:%G %a %n' /srv/scope/data/market
    ) || echo "STOPPED: fix the line above before going on"

**5. The two units, from the tag**, enabled but not started: the live code before the restart
may not know the sync. Fill `TAG=` with step c's tag:

    cd /srv/scope || exit 1
    TAG=
    ( set -eu
      [ -n "$TAG" ] || { echo "STOP: fill TAG= with the tag from step c"; exit 1; }
      for u in scope-market.service scope-market.timer; do
        git show "$TAG:deploy/$u" > "/etc/systemd/system/$u"
      done
      systemctl daemon-reload
      systemctl enable scope-market.timer
      systemctl is-enabled scope-market.timer
    ) || echo "STOPPED: fix the line above before going on"

Then step d as usual (its `cmp` lines find the units already in place). **6. After step d's
restart**, start the timer and see its next run:

    cd /srv/scope || exit 1
    ( set -eu
      systemctl start scope-market.timer
      systemctl is-active scope-market.timer
      systemctl list-timers scope-market.timer --no-pager
    ) || echo "STOPPED: fix the line above before going on"

Expected: `active`, and a next run within ten minutes. The next night's backup prints
`market bars copied to s3://<bucket>/market/`; step e's checks still apply.

## 6. Before the first partner uploads

The release gate, PRD section 10. None of it is optional and none of it is code:

1. Re-read `docs/runbooks/data-flow-map.md` against the running box, and remove
   its "not yet verified on a running server" line once it has been.
2. Confirm nothing external is reached: no analytics, no error reporter, no
   outbound client. The repository has none; check the box has none either.
3. Delete a fixture account on the server through the page. Confirm the file is
   gone from `/srv/scope/data/files` and the rows from the database, then note
   the date the last backup holding it ages out, and check it on that date.
4. Have someone who did not write it read the consent text, then set
   `reviewed=True` and bump the version in
   `services/production/accounts/consent.py`. **Until that happens the app
   refuses real accounts on purpose** — a real account reaching `/consent` gets
   the "not open yet" page, by design.

## When uploads are refused

The caps are in `services/production/journal/constants.py`, each with its argument.

- **A trader says uploads are refused for storage:** the disk has passed
  `UPLOADS_REFUSED_AT_DISK_PERCENT`. Nothing alerts on this. It's only in the log:
  `journalctl -u scope | grep "uploads refused"`, and `df -h /srv/scope`.
- **Someone can't sign up behind a shared connection:** the count is in memory, so
  `systemctl restart scope` clears it.

## What this does not cover

Postgres (ADR-005, Phase 1), a second app process, log shipping, uptime
monitoring. Each is additive; none is needed for a handful of traders.
