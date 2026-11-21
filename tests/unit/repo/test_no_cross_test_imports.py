"""TICKET-945: a test file never imports from another test file.

When a test file imports helpers or fixtures from another ``test_*.py``, editing one breaks
the other, and a fixture imported by name silently replaces any fixture of the same name
(hundreds of ``# noqa: F811`` were hiding that). Plain helpers and constants live in
``tests/helpers/``; fixtures live in a ``conftest.py`` or in the test file that uses them.

ALLOWED is every cross-test import still on main, as ``importer::module::name``. It may only
shrink: a new import fails here, and an entry whose import has gone must be deleted. Each
folder is cleared by its own ticket; TICKET-945 cleared tests/unit/api.
Imports from a conftest.py are not counted.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API = "tests/unit/api/"
F811_NOQA = re.compile(r"#\s*noqa\s*:[^#\n]*\bF811\b")

ALLOWED = frozenset(
    {
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_generation::load_trips",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_generation::session",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_generation::trader",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_version_label::_rewrite",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_version_label::day",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_version_label::first_upload",
        "tests/unit/journal/test_answers_follow_the_day.py::tests.unit.journal.test_version_label::second_upload",
        "tests/unit/journal/test_version_label.py::tests.unit.journal.test_generation::an_import",
        "tests/unit/journal/test_version_label.py::tests.unit.journal.test_generation::load_trips",
        "tests/unit/journal/test_version_label.py::tests.unit.journal.test_generation::session",
        "tests/unit/journal/test_version_label.py::tests.unit.journal.test_generation::trader",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::CE",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::LONG",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::PE",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::SHORT",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::T0",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::leg",
        "tests/unit/shared/test_option_direction.py::tests.unit.test_positions::one",
        "tests/unit/test_reconstruction_intraday.py::tests.unit.test_reconstruction::EQ",
        "tests/unit/test_reconstruction_intraday.py::tests.unit.test_reconstruction::T0",
        "tests/unit/test_reconstruction_intraday.py::tests.unit.test_reconstruction::fill",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::EQ",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::NIFTY",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::fill",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::prices",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::qtys",
        "tests/unit/test_sold_trades_accounted.py::tests.unit.test_reconstruction::sides",
    }
)


def is_test_module(dotted: str) -> bool:
    return dotted.rsplit(".", 1)[-1].startswith("test_")


def cross_test_imports(path: Path, root: Path) -> set[str]:
    """Every import in ``path`` of a test module, as importer::module::name."""
    rel = path.relative_to(root)
    here = list(rel.with_suffix("").parts)
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                module = ".".join(here[: -node.level] + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module != "tests" and not module.startswith("tests."):
                continue
            for alias in node.names:
                if is_test_module(module):
                    found.add(f"{rel.as_posix()}::{module}::{alias.name}")
                elif is_test_module(f"{module}.{alias.name}"):
                    found.add(f"{rel.as_posix()}::{module}.{alias.name}::<module>")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tests.") and is_test_module(alias.name):
                    found.add(f"{rel.as_posix()}::{alias.name}::<module>")
    return found


def scan(root: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted((root / "tests").rglob("*.py")):
        found |= cross_test_imports(path, root)
    return found


def in_slice(entry: str) -> bool:
    """TICKET-945's slice: anything imported by, or from a test file in, tests/unit/api."""
    return entry.startswith(API) or "::tests.unit.api.test_" in entry


def test_no_new_cross_test_imports():
    new = sorted(scan(ROOT) - ALLOWED)
    assert not new, (
        "a test file imports from another test file; move what it needs into tests/helpers/ "
        "(plain helpers) or a conftest.py (fixtures):\n" + "\n".join(new)
    )


def test_allow_list_only_shrinks():
    gone = sorted(ALLOWED - scan(ROOT))
    assert not gone, "these imports are gone; delete them from ALLOWED:\n" + "\n".join(gone)


def test_api_slice_is_never_allowed():
    assert not sorted(e for e in ALLOWED if in_slice(e))


def test_no_f811_noqa_under_tests_unit_api():
    hits = [
        f"{path.relative_to(ROOT).as_posix()}:{number}"
        for path in sorted((ROOT / API).rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if F811_NOQA.search(line)
    ]
    assert not hits, "a fixture is imported by name again:\n" + "\n".join(hits)


def test_scanner_sees_every_form(tmp_path):
    source = tmp_path / "tests" / "unit" / "x" / "test_new.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from tests.unit.api.test_upload import client\n"
        "from .test_other import helper\n"
        "import tests.unit.y.test_z\n"
        "from tests.unit.y import test_w\n"
        "from tests.helpers.upload import sign_up\n"
        "from tests.conftest import TEST_FILE_KEY\n"
        "def later():\n"
        "    from tests.unit.y.test_q import thing\n",
        encoding="utf-8",
    )
    here = "tests/unit/x/test_new.py"
    assert cross_test_imports(source, tmp_path) == {
        f"{here}::tests.unit.api.test_upload::client",
        f"{here}::tests.unit.x.test_other::helper",
        f"{here}::tests.unit.y.test_z::<module>",
        f"{here}::tests.unit.y.test_w::<module>",
        f"{here}::tests.unit.y.test_q::thing",
    }
