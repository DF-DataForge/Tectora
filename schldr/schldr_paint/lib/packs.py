# -*- coding: utf-8 -*-
"""Which pots to buy for a quantity of paint. No Odoo import; mirrored by
``static/src/plan_editor/lib/packs.js``.

Paint comes in a few sizes (1 L, 2.5 L, 5 L, 10 L). For a need of 4 L the
largest-first habit buys 2.5 + 1 + 1; one pot of 5 L is the better buy. So the
choice is worked out: every combination that covers the need is weighed and
the cheapest wins.

With a price on every size that is the real price. Without, a larger pot is
taken to be cheaper per litre (price ~ volume ^ 0.8), which is how paint is
priced and gives the choice a painter makes: 5 L for a need of 4, 5 + 1 for a
need of 6, 10 L for a need of 9.
"""
import math
from functools import reduce

SCALE = 1000  # volumes are worked in thousandths, so 0.75 L is exact
MAX_CELLS = 20000


def _weight(volume, price):
    return price if price else volume ** 0.8


def choose_packs(need, sizes):
    """The pots for ``need`` units out of ``sizes``, a list of volumes or of
    (volume, price) pairs. Returns [(volume, count)], largest first; an empty
    list when nothing is needed or there are no sizes."""
    packs = []
    for size in sizes:
        volume, price = size if isinstance(size, (tuple, list)) else (size, 0.0)
        if volume and volume > 0:
            packs.append((float(volume), float(price or 0.0)))
    if need <= 1e-9 or not packs:
        return []
    priced = all(price > 0 for _volume, price in packs)
    packs = sorted({volume: price for volume, price in packs}.items())
    units = [int(round(volume * SCALE)) for volume, _price in packs]
    weights = [_weight(volume, price if priced else 0.0) for volume, price in packs]
    step = reduce(math.gcd, units)
    units = [unit // step for unit in units]
    target = int(math.ceil(need * SCALE / step - 1e-9))

    counts = [0] * len(packs)
    # a very large need: fill up with the pot that is cheapest per litre first
    largest = max(units)
    if target + largest > MAX_CELLS:
        best = min(range(len(packs)), key=lambda i: (weights[i] / units[i], -units[i]))
        bulk = (target - MAX_CELLS // 2) // units[best]
        counts[best] += bulk
        target -= bulk * units[best]

    # cheapest way to reach exactly each volume up to need + largest pot
    limit = target + largest
    infinity = float("inf")
    cost = [infinity] * (limit + 1)
    pots = [0] * (limit + 1)
    last = [-1] * (limit + 1)
    cost[0] = 0.0
    for volume in range(1, limit + 1):
        for index, unit in enumerate(units):
            if unit > volume or cost[volume - unit] == infinity:
                continue
            candidate = cost[volume - unit] + weights[index]
            number = pots[volume - unit] + 1
            if candidate < cost[volume] - 1e-9 or (
                abs(candidate - cost[volume]) <= 1e-9 and number < pots[volume]
            ):
                cost[volume] = candidate
                pots[volume] = number
                last[volume] = index
    best_volume = min(
        (volume for volume in range(target, limit + 1) if cost[volume] < infinity),
        key=lambda volume: (round(cost[volume], 9), volume, pots[volume]),
    )
    volume = best_volume
    while volume > 0:
        index = last[volume]
        counts[index] += 1
        volume -= units[index]
    return [
        (packs[index][0], counts[index])
        for index in range(len(packs) - 1, -1, -1) if counts[index]
    ]


def packed_volume(chosen):
    return sum(volume * count for volume, count in chosen)


def describe(chosen, unit="L"):
    """'2 x 10 L + 1 x 2,5 L'."""
    parts = []
    for volume, count in chosen:
        text = ("%g" % volume).replace(".", ",")
        parts.append("%d x %s %s" % (count, text, unit))
    return " + ".join(parts)
