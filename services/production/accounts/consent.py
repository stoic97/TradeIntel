"""The consent text and the ledger rules (thesis 19.3, PRD 10).

PRD section 10's release gate says the consent text is published only after the
data-flow map is written and verified and the deletion runbook has been executed
end to end. ``require_reviewed`` refuses an unreviewed version for a real account:
it can be shown to a development-data account and in tests, and nowhere else.

Version 1 was reviewed on 22 October 2026: the deletion runbook was run on the
server through the page (docs/runbooks/deletion-log.md), the data-flow map was
corrected to the weekly backups the server actually keeps, and the rendered page
was read against that map by Rikk, who did not write it. Any change to the
wording below is a new version, unreviewed until someone reads it again.

Each purpose is a separate decision. Only DIAGNOSIS is required for the product to
run; refusing any other never degrades what the trader gets. The exact wording shown
is stored on each ledger row, so a question about what someone agreed to is answered
from the row rather than from whatever the template says today.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.shared.schemas import scope_v1 as s


class UnreviewedConsentText(Exception):
    """A draft consent version, asked for by a real account."""


@dataclass(frozen=True)
class Purpose:
    key: str
    enum: s.ConsentPurpose
    title: str
    body: str
    required: bool


@dataclass(frozen=True)
class ConsentText:
    version: str
    reviewed: bool
    what_we_store: str
    how_long: str
    who_can_access: str
    what_deletion_covers: str
    what_deletion_cannot_undo: str
    purposes: tuple[Purpose, ...]

    def purpose(self, key: str) -> Purpose:
        return next(p for p in self.purposes if p.key == key)


CURRENT = ConsentText(
    version="1",
    reviewed=True,
    what_we_store=(
        "The file you upload, exactly as your broker produced it. The reconstruction "
        "we build from it — your trades matched into round trips. And the Journals "
        "written from those trades. We also record which lines you open and how long "
        "you read them, so that a later version can put the lines that matter to you "
        "first; that is a record of what you read, never of anything you type. "
        "Nothing else about you."
    ),
    how_long="Until you delete it.",
    who_can_access=(
        "The two people who run the product: the founder, and the engineer who runs "
        "the server. No third party receives the file, and no external service "
        "touches anything derived from it — there is no analytics, no error "
        "reporting and no email in this product. If that ever changes, this page "
        "names the service before it does."
    ),
    what_deletion_covers=(
        "The file, every artefact derived from it, and every Journal. Backups roll "
        "off within 30 days, so your data is gone from those too. What we keep is "
        "the record that you consented and the record that you deleted — the proof "
        "that both happened."
    ),
    what_deletion_cannot_undo=(
        "Your file and everything derived from it can be deleted at any time. What "
        "cannot be undone is that looking at your data informed decisions we have "
        "already made about the engine. This is the same as any research "
        "partnership, and we say so plainly."
    ),
    purposes=(
        Purpose(
            key="diagnosis",
            enum=s.ConsentPurpose.DIAGNOSIS,
            title="Process my tradebook to produce my own record",
            body=(
                "We read your file, reconstruct your trades, and show you what they "
                "say. This is the product: without it there is nothing to run."
            ),
            required=True,
        ),
        Purpose(
            key="engine_testing",
            enum=s.ConsentPurpose.ENGINE_TESTING,
            title="Use my tradebook to check and calibrate the engine",
            body=(
                "Your history helps us find out where our reconstruction and our "
                "measurements are wrong. We do this by running our own code against "
                "your trades and comparing what it says with what your file shows. "
                "You can refuse this and still get everything else, exactly as it is."
            ),
            required=False,
        ),
    ),
)


def require_reviewed(text: ConsentText, *, development_data: bool) -> ConsentText:
    """Gate for anything a real trader reads.

    A development-data account may see a draft, because that is how the draft gets
    walked before review. A real account may not: the wording is a promise, and an
    unreviewed promise is one nobody has checked we can keep.
    """
    if text.reviewed or development_data:
        return text
    raise UnreviewedConsentText(
        f"consent text {text.version} has not been reviewed (PRD 10 release gate, "
        "step 4; counsel sign-off gates accepting tradebooks). Review it, set "
        "reviewed=True and bump the version before a partner account sees it."
    )


def wording_for(purpose: Purpose, text: ConsentText = CURRENT) -> str:
    """Exactly what the trader read for this purpose, stored on his ledger row."""
    return (
        f"[{text.version}] {purpose.title}. {purpose.body} "
        f"What we store: {text.what_we_store} "
        f"How long: {text.how_long} "
        f"Who can access it: {text.who_can_access} "
        f"Deletion: {text.what_deletion_covers} {text.what_deletion_cannot_undo}"
    )


# --- TICKET-896: consent for a recurring, read-only broker pull -----------------------
# A separate decision from the diagnosis consent, with its own words and its own version.
# CURRENT (version "1") is not touched, so nobody is asked to agree to it again. This text
# is a DRAFT: require_reviewed refuses it for a real account until someone who did not
# write it has read it against the connector and set reviewed=True.

READ_ONLY_PROMISE = (
    "read-only: we can fetch your trades, we can never place, change or cancel an order."
)


@dataclass(frozen=True)
class BrokerPullText:
    version: str
    reviewed: bool
    purpose: Purpose
    what_we_fetch: str
    how_often: str
    how_long: str
    how_to_stop: str
    what_stopping_keeps: str


BROKER_PULL = BrokerPullText(
    version="broker-1-draft",
    reviewed=False,
    purpose=Purpose(
        key="broker_pull",
        enum=s.ConsentPurpose.BROKER_PULL,
        title="Fetch my trades from my broker, read-only",
        body=(
            "This is separate from the file you uploaded. You let us fetch your trades "
            "from your broker again and again, until you disconnect. Without it you can "
            "still upload files by hand, exactly as before."
        ),
        required=False,
    ),
    what_we_fetch=(
        "Your trades from Dhan, the good months and the bad ones alike. Dhan is an "
        "outside service, and this connection is the one place this product talks to it. "
        "To fetch, we keep a connection key for your account, stored encrypted and never "
        "shown."
    ),
    how_often="Once each trading day, after the market closes.",
    how_long=CURRENT.how_long,
    how_to_stop=(
        "Press Disconnect in your settings. The key is deleted at once and nothing more "
        "is fetched."
    ),
    what_stopping_keeps=(
        "The trades already fetched and the reports built from them stay exactly as they "
        "are. Deleting your account removes the key and everything else, as above."
    ),
)


def broker_pull_wording(text: BrokerPullText = BROKER_PULL) -> str:
    """Exactly what the trader read for the broker connection, stored on his ledger row."""
    return (
        f"[{text.version}] {text.purpose.title}. {text.purpose.body} "
        f"What we fetch: {text.what_we_fetch} "
        f"How often: {text.how_often} "
        f"Promise: {READ_ONLY_PROMISE} "
        f"How long: {text.how_long} "
        f"Deletion: {CURRENT.what_deletion_covers} "
        f"How to stop: {text.how_to_stop} "
        f"After you stop: {text.what_stopping_keeps}"
    )


def version_in_force(purpose: s.ConsentPurpose) -> str:
    """The version a grant for this purpose has to carry to count today."""
    return BROKER_PULL.version if purpose is s.ConsentPurpose.BROKER_PULL else CURRENT.version
