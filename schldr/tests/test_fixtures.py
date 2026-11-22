"""The fixtures hold what the library measured when they were written: a
change in the numbers has to be a decision (python3 tests/make_fixtures.py),
not an accident."""
import json
from pathlib import Path

import pytest

from schldr_lib import document, measure

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_fixture(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    doc = document.load(fixture["document"])
    assert doc == fixture["expected"]["loaded"]
    result = measure.measure_document(doc, **fixture["options"])
    assert result["surfaces"] == fixture["expected"]["surfaces"]
    assert result["rooms"] == fixture["expected"]["rooms"]
    # every floor is covered by its ceiling parts
    for _level, room in document.iter_rooms(doc):
        ceiling = measure.Ceiling(room)
        if ceiling.slopes:
            floor = measure.geometry.area(ceiling.points)
            assert sum(ceiling.parts().values()) == pytest.approx(floor)
