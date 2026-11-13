"""The independent count and 891's agree on the demo history [TICKET-898, gate item 4].

Runs scripts/compare_898_with_891.py on the repo's demo tradebook and seeded synthetic bars
and requires its verdict: same figures, same denominators, same trips left out for the same
reasons, at the prior minute and at +5/+15/+30/+60. If either script changes without the
other, this fails and names the count that diverged. No figure is pinned here, so a change
to the demo fixture does not break it; only a disagreement does.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "scripts" / "compare_898_with_891.py"
_NAME = "compare_898_with_891_for_test"


def test_the_two_counts_agree_on_the_demo_history(capsys):
    spec = importlib.util.spec_from_file_location(_NAME, _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    try:
        spec.loader.exec_module(module)
        code = module.main([])
    finally:
        sys.modules.pop(_NAME, None)
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.strip().endswith("AGREE"), out
