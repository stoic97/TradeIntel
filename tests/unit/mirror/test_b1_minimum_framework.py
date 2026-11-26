"""TICKET-1083: the product's B1 minimum is the framework's B1 n_min.

Production never reads services/research at run time. The tie is this test, which reads the
registered row through the product's own reader (services.shared.prereg), so a change on either
side fails here, not on a page.
"""
from services.production.mirror import metrics as mx
from services.shared.prereg import reader


def test_b1_minimum_is_the_framework_b1_n_min_in_both_groups():
    b1 = reader.load().test("B1")
    assert b1.question == "post_loss_latency"
    assert b1.n_min.understood
    assert b1.n_min.condition == b1.n_min.comparison == mx.B1_MINIMUM
