#!/usr/bin/env python3
"""Write tests/fixtures/*.json: plan documents with what the Python library
measures in them. The JavaScript mirror is tested against the same files
(tests/js), so the two cannot drift apart unnoticed.

    python3 tests/make_fixtures.py          # rewrite the expected numbers
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import conftest  # noqa: E402,F401  (loads the library as schldr_lib)
from schldr_lib import document, measure  # noqa: E402

RECT = [[0, 0], [5000, 0], [5000, 4000], [0, 4000]]
L_SHAPE = [[0, 0], [6000, 0], [6000, 3000], [3000, 3000], [3000, 6000], [0, 6000]]


def walls(count, **special):
    return [dict({"id": "W%d" % (i + 1)}, **special.get("W%d" % (i + 1), {})) for i in range(count)]


DOCUMENTS = {
    "house": {
        "defaults": {"height": 2600, "assign": {
            "walls": [{"system": 1, "colour": 7}],
            "ceilings": [{"system": 2, "colour": 7}],
            "woodwork": [{"system": 3, "colour": 8}],
        }},
        "levels": [
            {"id": "L1", "name": "Gelijkvloers", "rooms": [
                {"id": "R1", "name": "Woonkamer", "height": 2600, "points": RECT, "walls": walls(4),
                 "has": {"floor": True, "moulding": True},
                 "openings": [
                     {"id": "O1", "wall": "W1", "kind": "door", "offset": 500, "width": 930,
                      "height": 2115, "leaf": True, "frame": True},
                     {"id": "O2", "wall": "W2", "kind": "window", "offset": 1000, "width": 1800,
                      "height": 1400, "sill": 900, "reveal": 180, "frame": True},
                     {"id": "O3", "wall": "W3", "kind": "window", "offset": 300, "width": 600,
                      "height": 600, "sill": 1500},
                     {"id": "O4", "wall": "W4", "kind": "exclusion", "offset": 0, "width": 2500,
                      "height": 1200},
                 ],
                 "items": [
                     {"id": "I1", "kind": "radiator", "width": 1200, "height": 600, "factor": 2.5},
                     {"id": "I2", "kind": "custom", "group": "woodwork", "name": "Trapleuning",
                      "length": 3200},
                 ],
                 "assign": {"R1:wall:W3": [{"system": 1, "colour": 9}], "R1:floor": []}},
                {"id": "R2", "name": "Keuken", "height": 2500, "points": L_SHAPE,
                 "walls": walls(6, W4={"virtual": True}, W2={"h": [2500, 3400]})},
            ]},
            {"id": "L2", "name": "Zolder", "rooms": [
                {"id": "R3", "name": "Slaapkamer", "height": 2400, "points": RECT, "walls": walls(4),
                 "slopes": [{"id": "S1", "wall": "W1", "knee": 1000, "pitch": 45},
                            {"id": "S2", "wall": "W3", "knee": 800, "pitch": 38}],
                 "openings": [{"id": "O5", "wall": "W2", "kind": "window", "offset": 200,
                               "width": 1000, "height": 1500, "sill": 500, "reveal": 100}]},
                {"id": "R4", "name": "Bergruimte", "height": 4000, "points": L_SHAPE, "walls": walls(6),
                 "slopes": [{"id": "S3", "wall": "W1", "knee": 600, "pitch": 40},
                            {"id": "S4", "wall": "W6", "knee": 600, "pitch": 40}]},
            ]},
        ],
    },
}
OPTIONS = {"deduct_min_area": 0.5}
SYSTEMS = {
    1: {"layers": [
        {"product": 10, "coats": 1, "rate": 8.0, "waste": 0.0, "tinted": False},
        {"product": 20, "coats": 2, "rate": 10.0, "waste": 10.0, "dilution": 5.0, "tinted": True},
    ]},
    2: {"layers": [{"product": 20, "coats": 2, "rate": 9.0, "waste": 10.0, "tinted": True}]},
    3: {"layers": [{"product": 30, "coats": 2, "rate": 12.0, "waste": 5.0, "tinted": True}]},
}


def main():
    for name, raw in DOCUMENTS.items():
        doc = document.load(raw)
        result = measure.measure_document(doc, **OPTIONS)
        assigned = measure.assignments(doc, result["surfaces"])
        needs = measure.material_needs(result["surfaces"], assigned, SYSTEMS)
        fixture = {
            "document": raw,
            "options": OPTIONS,
            "systems": {str(key): value for key, value in SYSTEMS.items()},
            "expected": {
                "loaded": doc,
                "surfaces": result["surfaces"],
                "rooms": result["rooms"],
                "assignments": assigned,
                "needs": {
                    "%s|%s" % (product, colour or 0): round(quantity, 6)
                    for (product, colour), quantity in needs.items()
                },
            },
        }
        path = HERE / "fixtures" / ("%s.json" % name)
        path.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("%s: %d surfaces" % (path.name, len(result["surfaces"])))


if __name__ == "__main__":
    main()
