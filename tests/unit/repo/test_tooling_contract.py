"""TICKET-943 - the tooling config says what it does (audit findings M1, M7).

Before this ticket: [tool.ruff] set no `select`, so only ruff's defaults ran and 22
`noqa` directives named rules that were switched off; mypy covered services/shared
only; scipy was imported in four places and declared nowhere; and the research
dependencies had no upper bounds, against ADR-004's own rule.

These assertions are the contract. Each one failed on main at f896a58.
"""

import pathlib
import tomllib

import pytest

REQUIRED_RUFF_RULES = {"E", "F", "I", "B", "UP", "DTZ", "BLE", "RUF100"}
FORMATTER_OWNS_WIDTH = ("tests/**", "scripts/**")
BOUNDED_RESEARCH_DEPS = {"numpyro", "pymc", "nutpie", "arviz"}
E501_SRC_EXCEPTIONS = {"services/production/ctr/adapters/groww_orders.py"}
PRODUCTION_RELAXED = {
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "disallow_untyped_calls",
    "disallow_untyped_decorators",
    "disallow_any_generics",
    "warn_return_any",
}


def _root() -> pathlib.Path:
    for parent in pathlib.Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("no pyproject.toml above " + str(__file__))


@pytest.fixture(scope="module")
def cfg() -> dict:
    return tomllib.loads((_root() / "pyproject.toml").read_text(encoding="utf-8"))


def _research_group(cfg: dict) -> list[str]:
    groups = cfg.get("dependency-groups", {})
    assert "research" in groups, "no research dependency group"
    return list(groups["research"])


def _name_of(spec: str) -> str:
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        spec = spec.split(sep)[0]
    return spec.strip().lower().replace("_", "-")


def test_ruff_runs_a_real_rule_set(cfg):
    select = set(cfg["tool"]["ruff"]["lint"]["select"])
    missing = REQUIRED_RUFF_RULES - select
    assert not missing, f"ruff lint select is missing {sorted(missing)}"


def test_up042_is_ignored_with_its_own_ticket(cfg):
    """StrEnum changes what str(member) returns; converting the 19 classes is its
    own ticket, so UP042 is off here on purpose rather than by omission."""
    assert "UP042" in cfg["tool"]["ruff"]["lint"].get("ignore", [])


@pytest.mark.parametrize("glob", FORMATTER_OWNS_WIDTH)
def test_the_formatter_owns_line_width_in_tests_and_scripts(cfg, glob):
    ignores = cfg["tool"]["ruff"]["lint"]["per-file-ignores"]
    assert "E501" in ignores.get(glob, []), f"{glob} should let the formatter own E501"


def test_e501_still_applies_to_src(cfg):
    """One documented exception: the Groww adapter's docstring quotes the broker's
    CSV header verbatim, 106 chars before indentation, and a noqa cannot go inside
    a docstring. Any other src-level E501 ignore is a regression."""
    ignores = cfg["tool"]["ruff"]["lint"]["per-file-ignores"]
    src = {g for g in ignores if g.startswith("services")}
    assert src == E501_SRC_EXCEPTIONS, f"unexpected src E501 ignores: {src}"


def test_mypy_covers_production_and_keeps_shared(cfg):
    files = cfg["tool"]["mypy"]["files"]
    assert "services/production" in files, f"production not type-checked: {files}"
    assert "services/shared" in files, f"shared lost coverage: {files}"
    assert cfg["tool"]["mypy"]["strict"] is True, "shared must stay strict"


def test_production_starts_without_the_strict_flags(cfg):
    overrides = cfg["tool"]["mypy"].get("overrides", [])
    block = [o for o in overrides if o.get("module") == "services.production.*"]
    assert block, "no [[tool.mypy.overrides]] for services.production.*"
    relaxed = {k for k, v in block[0].items() if k != "module" and v is False}
    missing = PRODUCTION_RELAXED - relaxed
    assert not missing, f"production override is missing {sorted(missing)}"


def test_scipy_is_declared(cfg):
    names = {_name_of(s) for s in _research_group(cfg)}
    assert "scipy" in names, "scipy is imported in four files but declared nowhere"


@pytest.mark.parametrize("dep", sorted(BOUNDED_RESEARCH_DEPS))
def test_research_deps_are_bounded(cfg, dep):
    specs = {_name_of(s): s for s in _research_group(cfg)}
    assert dep in specs, f"{dep} missing from the research group"
    assert "<" in specs[dep], f"ADR-004: {specs[dep]} has no upper bound"


def test_research_is_opt_in(cfg):
    groups = cfg["tool"]["uv"]["default-groups"]
    assert groups == ["dev"], f"default-groups is {groups}; research must be opt-in"


def test_ci_installs_the_research_group_for_the_research_tests():
    """default-groups no longer carries research, so CI has to ask for it:
    tests/unit/engine, evaluation and models need scipy and pymc."""
    ci = (_root() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--group research" in ci, "ci.yml must sync the research group"


def test_ci_checks_formatting_and_types():
    ci = (_root() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff format --check" in ci, "ci.yml does not check formatting"
    assert "mypy" in ci, "ci.yml does not run mypy"


def test_readme_documents_the_research_group():
    readme = (_root() / "README.md").read_text(encoding="utf-8")
    assert "--group research" in readme, "README must document uv sync --group research"
