"""`make hash-check`: the pre-commitment hash, checked as methodology §4 asks (TICKET-937).

Before the lock there is nothing to check: the framework is still `status: draft`, the
`.sha256` file does not exist yet, and `shasum -c` on a missing file failed every run, which
taught everyone to ignore the check. So:

* not locked yet (`status: draft`, no `.sha256`)  -> say so, exit 0;
* locked (a `.sha256` exists)                     -> the digest must match, else exit 1;
* `status: locked` but no `.sha256`                -> exit 1: a lock nobody can check is no lock;
* a `.sha256` while still `status: draft`          -> exit 1: the hash was written early.

The digest is the plain SHA-256 of the file's bytes, in `shasum -a 256` format, so the file
`make hash-lock` writes is the file this reads.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

PREREG = Path("services/research/prereg/framework_v1.yaml")


def status(framework: Path) -> str:
    found = re.search(r"^\s*status:\s*(\w+)", framework.read_text(encoding="utf-8"), re.MULTILINE)
    return found.group(1) if found else "unknown"


def check(framework: Path = PREREG) -> tuple[int, str]:
    lock = framework.with_name(framework.name + ".sha256")
    state = status(framework)
    if not lock.exists():
        if state == "locked":
            return 1, f"FAIL: {framework} says status: locked but {lock.name} does not exist"
        return 0, f"not locked yet: {framework} is status: {state}; nothing to check until the lock"
    if state != "locked":
        return 1, f"FAIL: {lock.name} exists but {framework} is still status: {state}"
    recorded = lock.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(framework.read_bytes()).hexdigest()
    if recorded != actual:
        return 1, f"FAIL: {framework} has changed since the lock ({actual[:12]}… ≠ {recorded[:12]}…)"
    return 0, f"OK: {framework} matches its locked hash {recorded[:12]}…"


def main(argv: list[str]) -> int:
    code, message = check(Path(argv[1]) if len(argv) > 1 else PREREG)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
