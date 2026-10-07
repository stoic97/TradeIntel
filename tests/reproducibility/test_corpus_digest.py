"""Regeneration test for corpus A (Methodology §7, §13; Research Spec §12.1).

A small corpus - every 100-trip cell at theta_min, one clean null, one adversarial
null - is generated on a seeded synthetic market and its ``decision_sha256`` is
pinned. The decision digest holds no float, so it must be identical on every
machine and every numpy that the lock admits; if it moves, a change altered what
the generator decides (a trade, a label, a cell), and that is never silent.

Updating the pinned value is a deliberate act, like regenerating a golden: say
why in the commit, and never to make a failing run pass.
"""
from services.research.evaluation.synthetic import corpus as cp
from services.research.evaluation.synthetic import export as ex

PINNED_DECISION_SHA256 = "108fe44f03c94de5d60acb97be24c7720f64002251cae1fa6f222584706d7230"


def _small_corpus():
    market = cp.synthetic_market(seed=1, n_days=700)
    cells = [c for c in cp.grid() if c.n_trades == 100 and c.multiple == 1]
    histories = [cp.planted_history(market, c, 0) for c in cells]
    histories += [cp.clean_null(0), cp.adversarial_null(market, 0)]
    return market, histories


def test_the_small_corpus_decides_exactly_what_it_decided_when_pinned(tmp_path):
    market, histories = _small_corpus()
    manifest = ex.write_corpus(histories, market, tmp_path, {})
    assert manifest["histories"] == {"adversarial_null": 1, "clean_null": 1, "planted": 17}
    assert manifest["decision_sha256"] == PINNED_DECISION_SHA256


def test_two_builds_in_one_process_are_byte_identical(tmp_path):
    market, histories = _small_corpus()
    a = ex.write_corpus(histories, market, tmp_path / "a", {})
    b = ex.write_corpus(histories, market, tmp_path / "b", {})
    assert a == b
