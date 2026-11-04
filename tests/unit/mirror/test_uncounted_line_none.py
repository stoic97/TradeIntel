"""With nothing set aside the line is gone, by itself [TICKET-811]."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path", ["/", "/mirror", "/mirror/reveal", "/mirror/chapter/1", "/mirror/fact/money"]
)
def test_no_trades_set_aside_means_no_line(client, path):
    assert "not yet counted" not in client.get(path).text
