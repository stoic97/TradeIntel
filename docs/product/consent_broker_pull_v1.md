# Consent for a recurring, read-only broker pull

TICKET-896. Status: **draft wording, unreviewed**. Decisions of 12 Nov 2026 (Pawan) are applied as written. Two points are open with Pawan and are marked below.

## The decision

Uploading a file is agreeing to one diagnosis of that file. A broker connection is a standing permission to fetch his trades again and again, including months he would not have chosen to send. It is its own consent, never an amendment to the diagnosis consent.

Settled: connections are for subscribers only (free visitors upload by hand); disconnect is one action that deletes the key at once and keeps his reports; retention is the existing wording, no new period; the promise is the sentence in `READ_ONLY_PROMISE`; `/delete` removes the stored key.

## The wording

The words live in `services/production/accounts/consent.py` (`BROKER_PULL`, `broker_pull_wording()`). It covers what we fetch (and that Dhan is named), how often, the read-only promise, how long, how to stop, and what stopping keeps. Version `broker-1-draft`, `reviewed=False`: `require_reviewed` refuses it for a real account, so nobody can grant it until it is reviewed and the version is bumped.

## What changes in the consent ledger

- A new kind, `broker_pull` (`ConsentPurpose.BROKER_PULL`). No table change: `consent_event.purpose` is plain text.
- Grant and withdrawal are new rows, as for every consent. Each row stores the exact words shown and its own `terms_version`.
- A grant counts only against its own text's version (`consent.version_in_force`). Before this change every purpose was compared with the diagnosis text's version, which would have shown a broker grant as "on an older text" and sent the trader back to the consent screen.
- The diagnosis text stays at version `1`; nobody is asked to agree to it again.
- New table `broker_connection` (migration `0013`): trader, broker, encrypted key, time. It is deleted on disconnect and by `/delete`; `deletion.py` names it, `nothing_remains` checks it.
- Not built here: the connect and disconnect pages, the subscriber check (no subscriber flag exists in the code yet), and the fetching itself.

## What today's consent says that a scheduled pull would contradict

1. `what_we_store`: "The file you upload, exactly as your broker produced it." A pull has no file; the trades arrive through the broker's service.
2. `who_can_access`: "No external service touches anything derived from it ... this page names the service before it does." A pull calls Dhan. The broker text names Dhan; the diagnosis text does not need to change while the connection is off.
3. The sign-up door (`api/door.py`): "You give us: The trade file your broker lets you download. Never your broker login." A connection holds a key made from the trader's broker login. Also "Cost: Free today" against subscribers-only.
4. `what_deletion_covers` does not mention a stored key. The broker text adds it.
5. The delete pages say two rows survive (the consent record and the deletion record). `delete_trader` deletes the consent rows, and `admin.html` says so; only the deletion record survives. This predates 896 and is not fixed here.
6. `docs/runbooks/data-flow-map.md` has no row for the key. It needs one before the text is reviewed.

## Open with Pawan

- The promise "we can never place, change or cancel an order" against `broker_connector_note_v1.md`: Dhan documents no read-only token, only a static-IP rule on the trader's account.
- How often: "once each trading day" (this draft) or only when the trader opens Scope, discarding the key after each pull (the 901 note).