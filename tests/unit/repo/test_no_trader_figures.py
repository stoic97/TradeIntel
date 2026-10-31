"""No trader-derived figure in the repository, ever (PRD 10, PRD 14).

> *"The first trader's figures — his budget, his worst hour, his five days, what
> he pays for his charting tool — are his, and if any becomes a constant in the
> code the product has been fitted to one man."*

A figure from a real history reaches code by being typed in while someone is
debugging against it, and it stays because it works. This is the cheap check the
PRD asks for: large numbers in code that is not a fixture, each one either
justified here or not there at all.

It cannot tell a trader's rupees from a byte count, so it does not try. It makes
every large constant deliberate: to add one you add a line here saying what it is.
That is the whole mechanism, and it is worth exactly as much as the care taken
when a new line is added to ALLOWED.
"""

from __future__ import annotations

import re
from pathlib import Path

SCANNED = ("services",)
SKIP_PARTS = {"__pycache__", "fixtures", "prereg"}

# Numbers that are allowed to be in the code, and why. A value is allowed
# everywhere it appears; the reason is for whoever reads this next.
ALLOWED: dict[int, str] = {
    1000: "sampler draws and warmup; and a dwell cap written as 1000 * 60 * 30",
    1024: "bytes in a kibibyte, in the upload size cap",
    1224: "histories in the synthetic corpus; generated here, from no one",
    3000: "trips per run in a synthetic sweep",
    4000: "sampler draws, and the floats per parameter they come to",
    2000: "bootstrap resamples",
    2007: "a citation year (Papaspiliopoulos, Roberts and Skold)",
    2018: "a citation year",
    2020: "a citation year, and a synthetic series start",
    2026: "the current year, in dates and in examples",
    5000: "the strike in the synthetic instrument used in examples and fixtures",
    8000: "the port the local development server listens on",
    50000: "the upload row cap",
    1_000_000: "a synthetic corpus id base, so two generators cannot collide",
    12345: "the digits 1 to 5, the plain rupee example in formatting.py; a pattern",
    1234567: "the digits 1 to 7, showing Indian grouping (12,34,567) in formatting.py",
    2212: "U+2212, the true minus sign, named by its code point in formatting.py",
    2_000_000: "the same, for the clean-null corpus",
    3_000_000: "the same, for the adversarial corpus",
    3828: (
        "the number of rows in the first real export, cited as the provenance of "
        "the four facts the Dhan adapter establishes rather than assumes. A count "
        "of lines in a file is not a figure from anyone's trading, and dropping it "
        "would leave those four facts looking like assertions. Kept deliberately."
    ),
}

# Comma groups included on purpose: prose writes 3,828 and the first version of
# this check could not see it, which is the one number in the repository that
# most needed a decision recorded against it.
NUMBER = re.compile(r"(?<![\w.])(\d[\d,_]*\d)(?![\w.])")
THRESHOLD = 1000


def files() -> list[Path]:
    out: list[Path] = []
    for root in SCANNED:
        for path in Path(root).rglob("*"):
            if path.suffix not in (".py", ".html"):
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            out.append(path)
    return out


def test_there_are_files_to_scan():
    assert len(files()) > 30, "the glob matched almost nothing"


def test_no_unexplained_large_number_is_in_the_code():
    found: dict[int, list[str]] = {}
    for path in files():
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            if "noqa: figure" in line:
                continue
            for raw in NUMBER.findall(line):
                value = int(raw.replace("_", "").replace(",", ""))
                if value < THRESHOLD or value in ALLOWED:
                    continue
                found.setdefault(value, []).append(f"{path}:{line_no}")

    assert not found, (
        "large numbers in non-fixture code. Each is either a trader's figure, "
        "which must go, or a constant, which needs a line in ALLOWED saying what "
        "it is:\n"
        + "\n".join(f"  {value}: {', '.join(where)}"
                    for value, where in sorted(found.items()))
    )
