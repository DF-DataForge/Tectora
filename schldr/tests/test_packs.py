import pytest

from schldr_lib import packs

SIZES = [1, 2.5, 5, 10]


@pytest.mark.parametrize("need, expected", [
    (0, []),
    (0.4, [(1, 1)]),
    (1, [(1, 1)]),
    (2.2, [(2.5, 1)]),
    (4, [(5, 1)]),              # not 2.5 + 1 + 1
    (6, [(5, 1), (1, 1)]),
    (9, [(10, 1)]),
    (12.4, [(10, 1), (2.5, 1)]),
    (23, [(10, 2), (2.5, 1), (1, 1)]),
])
def test_unpriced(need, expected):
    assert packs.choose_packs(need, SIZES) == expected


def test_priced_takes_the_cheapest_cover():
    # a 5 L pot on offer: cheaper than 2.5 + 1
    assert packs.choose_packs(3.2, [(1, 20), (2.5, 45), (5, 60)]) == [(5, 1)]
    assert packs.choose_packs(3.2, [(1, 20), (2.5, 45), (5, 90)]) == [(2.5, 1), (1, 1)]


def test_always_covers_the_need():
    for tenths in range(1, 400):
        need = tenths / 10.0
        assert packs.packed_volume(packs.choose_packs(need, [0.75, 2.5, 10])) >= need - 1e-9


def test_large_need():
    chosen = packs.choose_packs(1234.5, [0.25, 1, 2.5, 10])
    assert 1234.5 <= packs.packed_volume(chosen) <= 1235.0
    assert chosen[0] == (10, 123)


def test_describe():
    assert packs.describe([(10, 2), (2.5, 1)]) == "2 x 10 L + 1 x 2,5 L"
