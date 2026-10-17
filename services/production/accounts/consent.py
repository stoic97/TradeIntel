"""The consent text and the ledger rules (thesis 19.3, PRD 10).

The text below is a DRAFT. PRD section 10's release gate says the consent text is
published only after the data-flow map is written and verified and the deletion
runbook has been executed end to end, and the face roadmap adds counsel's sign-off
before any tradebook is accepted. So ``require_reviewed`` refuses this version for a
real account: it can be shown to a development-data account and in tests, and
nowhere else, until someone reviews it and bumps the version.

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
    version="0-draft",
    reviewed=False,
    what_we_store=(
        "The file you upload, exactly as your broker produced it. The reconstruction "
        "we build from it — your trades matched into round trips. And the Journals "
        "written from those trades. Nothing else about you."
    ),
    how_long=(
        "Until you delete it. If you do not sign in for 24 months we delete it "
        "ourselves and tell you we have."
    ),
    who_can_access=(
        "The founder, who is the only person with access to the server. No third "
        "party receives the file, and no external service touches anything derived "
        "from it — there is no analytics, no error reporting and no email in this "
        "product. If that ever changes, this page names the service before it does."
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
