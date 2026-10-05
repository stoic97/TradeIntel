"""Step A, cycle 1 - the synthetic market layer.

The generator's traders act on a price path. Until the fund's MCX crude series is
confirmed (doubt D4), the path is synthetic and seeded. These tests pin what the
rest of the generator relies on: same seed -> same bytes, a crude trading day,
sane bars, and volatility clustering only when asked for (the adversarial null
class needs it; the clean class must not have it).
"""
import numpy as np
import pytest

from services.research.evaluation.synthetic.market import (
    BARS_PER_DAY,
    SESSION_CLOSE_MIN,
    SESSION_OPEN_MIN,
    MarketConfig,
    generate_bars,
)


def test_same_seed_gives_identical_bytes():
    a = generate_bars(seed=7, n_days=20)
    b = generate_bars(seed=7, n_days=20)
    assert a.content_hash() == b.content_hash()


def test_different_seed_gives_different_path():
    a = generate_bars(seed=7, n_days=20)
    b = generate_bars(seed=8, n_days=20)
    assert a.content_hash() != b.content_hash()


def test_one_bar_per_minute_of_the_mcx_session():
    bars = generate_bars(seed=1, n_days=3)
    assert BARS_PER_DAY == SESSION_CLOSE_MIN - SESSION_OPEN_MIN
    assert len(bars.close) == 3 * BARS_PER_DAY
    assert bars.minute.min() == SESSION_OPEN_MIN
    assert bars.minute.max() == SESSION_CLOSE_MIN - 1
    assert list(np.unique(bars.day)) == [0, 1, 2]


def test_bars_are_internally_consistent():
    bars = generate_bars(seed=3, n_days=10)
    assert (bars.low > 0).all()
    assert (bars.low <= np.minimum(bars.open, bars.close)).all()
    assert (bars.high >= np.maximum(bars.open, bars.close)).all()


def _abs_return_autocorr(bars):
    r = np.abs(np.diff(np.log(bars.close)))
    return np.corrcoef(r[:-1], r[1:])[0, 1]


def test_volatility_clusters_only_when_asked():
    calm = generate_bars(seed=11, n_days=60, config=MarketConfig(vol_clustering=False))
    clustered = generate_bars(seed=11, n_days=60, config=MarketConfig(vol_clustering=True))
    assert abs(_abs_return_autocorr(calm)) < 0.05
    assert _abs_return_autocorr(clustered) > 0.10


@pytest.mark.parametrize("seed,n_days", [(-1, 5), (1, 0)])
def test_refuses_bad_arguments(seed, n_days):
    with pytest.raises(ValueError):
        generate_bars(seed=seed, n_days=n_days)
