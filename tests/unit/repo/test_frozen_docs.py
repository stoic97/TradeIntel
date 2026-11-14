"""A frozen document changes only by a version bump; an Accepted ADR is never edited (SR-011).

TICKET-931 (repo audit, finding C3). The product's claim is that every number traces back to
rules fixed in advance. The research spec changed three times after its freeze under the same
version, and ADR-007 was rewritten in place, with `git blame` the only record of either.

Each frozen file is held here by its version and its digest. Edit one and this fails until,
in the same commit:

* a document's version is bumped in its title, and a dated row naming that version, what
  changed, why and the ticket is added at the top of its change log; or an ADR gains a dated
  entry in its Amendments section, and its Status line says "amended <date>";
* the entry below is updated to the new version and digest.

The digest is of the text with line endings normalised, so a checkout on Windows is not an edit.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import NamedTuple


class Frozen(NamedTuple):
    version: str  # what the title (a document) or the Status line (an ADR) says
    sha256: str


FROZEN: dict[str, Frozen] = {
    "docs/trade_dna_research_spec_v1_0.md": Frozen(
        "v1.0.3", "9a1d561e56db5982ab2fb687033f45f7b1a2a10489183cb4bd9b822a4cf5e23c"),
    "docs/trade_dna_brainstorm_workbook_v1.1_final.md": Frozen(
        "v1.1.1", "87be5b1133475b76b0854e8f3919710de88a1ea23f6b1c9e4904be3836cff1c7"),
    "docs/trade_dna_product_thesis_v1.5.md": Frozen(
        "v1.5", "3d09d024d44bc2459fe7901425d4595e0accffd73c0f8ae7d824f635a05cf963"),
    "docs/trade_dna_product_thesis_v1.4.md": Frozen(
        "v1.4", "d2e775ec1bc95a3bda4e463d59a2fd6ae6eb19cf1e537e771588f1fc7ccbaa16"),
    "docs/adr/ADR-001-canonical-trade-record.md": Frozen(
        "Accepted", "0bf5938ba648f029b2f5eba933294bd6f105f0f7e2e2b2cfcf8ebdc1b7154dc8"),
    "docs/adr/ADR-002-the-wall.md": Frozen(
        "Accepted", "c25d865e88294cb80bb1c8c161af8fab1a4c2615043f886dd5d21f3ce53319d9"),
    "docs/adr/ADR-003-precommitment-hash.md": Frozen(
        "Accepted", "1c47cca5ffb3aaaf39bb82ddbd7a17aae73720a23e81a7c1342540fcd163bb38"),
    "docs/adr/ADR-004-stage0-tech-stack.md": Frozen(
        "Accepted", "9bfa7ec4207114ca95ac85c3455ce8e69c5145d41fbe33f4a63ea13ad82a7ef8"),
    "docs/adr/ADR-005-storage-and-reproducible-runs.md": Frozen(
        "Accepted", "23f58f0424b35c41c789ce4f88bd0b8ae594d8682fef0fc0677385cf93022865"),
    "docs/adr/ADR-006-sampler.md": Frozen(
        "Accepted", "9125225d6d1f4eb018668c560be2eda0ab071b14cb3f5fe9c8a7832575c0631c"),
    "docs/adr/ADR-007-scope-v1-runtime.md": Frozen(
        "amended 2026-11-05", "7c52c751d3e06fbb20712c03075eaf302913b9e51bd607e09d0f1f6e395a8cee"),
    "docs/adr/ADR-008-market-data-source.md": Frozen(
        "Accepted", "9e6e74f544e82e465b8757ac7e34694a47e532d519dd050b945a76e760569a92"),
}

HOW = ("is frozen (SR-011). Bump its version and add a dated change-log row (an ADR: an "
       "Amendments entry), then update its entry in tests/unit/repo/test_frozen_docs.py")


def text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")


def digest(path: str) -> str:
    return hashlib.sha256(text(path).encode("utf-8")).hexdigest()


def head(path: str, lines: int = 4) -> str:
    return "\n".join(text(path).splitlines()[:lines])


def test_no_frozen_file_has_changed_without_its_version_and_digest():
    changed = [p for p, f in FROZEN.items() if digest(p) != f.sha256]
    assert changed == [], f"{changed} {HOW}"


def test_each_frozen_file_says_the_version_it_is_held_at():
    for path, frozen in FROZEN.items():
        where = text(path).splitlines()[0] if not path.startswith("docs/adr/") else head(path)
        assert frozen.version in where, f"{path}: held at {frozen.version!r}, which it does not say"


def test_a_change_log_starts_with_the_version_the_document_is_at():
    """Where a document has a change log, its newest row is the version it is held at."""
    for path, frozen in FROZEN.items():
        body = text(path)
        if "**Change log**" not in body:
            continue
        rows = re.findall(r"^\| (v[\d.]+)[^|]*\|", body.split("**Change log**", 1)[1], re.MULTILINE)
        assert rows and rows[0] == frozen.version, f"{path}: newest row {rows[:1]}, held at {frozen.version}"


def test_an_amended_adr_carries_the_dated_amendment_its_status_names():
    for path, frozen in FROZEN.items():
        dated = re.search(r"amended (\d{4}-\d{2}-\d{2})", frozen.version)
        if dated:
            amendments = text(path).split("## Amendments", 1)
            assert len(amendments) == 2, f"{path}: amended, but has no Amendments section"
            assert f"### {dated.group(1)}" in amendments[1], f"{path}: no entry dated {dated.group(1)}"


def test_the_amended_research_spec_and_workbook_record_every_post_freeze_change():
    """Gate 1 of TICKET-931: each change made in place after the freeze has its row."""
    for path, commits in {
        "docs/trade_dna_research_spec_v1_0.md": ("b868b55", "47a11cc", "a4f9836"),
        "docs/trade_dna_brainstorm_workbook_v1.1_final.md": ("b868b55",),
        "docs/adr/ADR-007-scope-v1-runtime.md": ("bc4e3fb",),
    }.items():
        for commit in commits:
            assert commit in text(path), f"{path}: no record of {commit}"


def test_every_accepted_adr_is_held_here():
    """A new ADR is frozen the moment it is accepted, so it is added here when it is."""
    for path in sorted(Path("docs/adr").glob("ADR-*.md")):
        if re.search(r"Status[.:*\s]*\**Accepted", head(str(path))):
            assert str(path) in FROZEN, f"{path} is Accepted: add it to FROZEN"
