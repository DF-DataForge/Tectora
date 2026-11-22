import json

import pytest

from schldr_lib import document


def test_empty_text_is_an_empty_document():
    doc = document.load("")
    assert doc["schema"] == 1
    assert doc["levels"][0]["rooms"] == []


def test_every_part_gets_an_id_once():
    doc = document.load({"levels": [{"rooms": [
        {"points": [[0, 0], [1000, 0], [1000, 1000]], "walls": [{"id": "W1"}, {"id": "W1"}]},
    ]}]})
    walls = doc["levels"][0]["rooms"][0]["walls"]
    assert len(walls) == 3
    assert len({wall["id"] for wall in walls}) == 3
    assert walls[0]["id"] == "W1"
    assert document.load(document.dump(doc)) == doc


def test_sizes_become_whole_millimetres():
    doc = document.load(json.dumps({"levels": [{"rooms": [
        {"points": [[0.4, 0], ["1000.6", 0], [1000, 1000]], "height": "2500.2"},
    ]}]}))
    room = doc["levels"][0]["rooms"][0]
    assert room["points"][:2] == [[0, 0], [1001, 0]]
    assert room["height"] == 2500


def test_parts_on_a_wall_that_is_gone_are_dropped():
    doc = document.load({"levels": [{"rooms": [{
        "points": [[0, 0], [1000, 0], [1000, 1000]],
        "walls": [{"id": "W1"}, {"id": "W2"}, {"id": "W3"}],
        "openings": [{"wall": "W9", "width": 900, "height": 2000}, {"wall": "W2", "width": 900, "height": 2000}],
        "slopes": [{"wall": "W9", "knee": 1000}],
    }]}]})
    room = doc["levels"][0]["rooms"][0]
    assert [o["wall"] for o in room["openings"]] == ["W2"]
    assert room["slopes"] == []


def test_not_a_document():
    with pytest.raises(document.DocumentError):
        document.load("{nope")
    with pytest.raises(document.DocumentError):
        document.load({"schema": 99})


def test_a_copied_room_keeps_its_slopes_openings_and_assignments():
    room = {
        "id": "R1", "points": [[0, 0], [1000, 0], [1000, 1000]],
        "walls": [{"id": "W1"}, {"id": "W2"}, {"id": "W3"}],
        "slopes": [{"id": "S1", "wall": "W2", "knee": 1000}],
        "openings": [{"id": "O1", "wall": "W3", "width": 900, "height": 2000, "leaf": True}],
        "assign": {"R1:wall:W2": [{"system": 4}], "O1:leaf": [{"system": 5}]},
    }
    doc = document.load({"levels": [{"rooms": [room, room]}]})
    first, copy = doc["levels"][0]["rooms"]
    assert first["slopes"][0]["wall"] == "W2"
    wall = copy["walls"][1]["id"]
    assert wall != "W2"
    assert copy["slopes"][0]["wall"] == wall
    assert copy["openings"][0]["wall"] == copy["walls"][2]["id"]
    assert set(copy["assign"]) == {
        "%s:wall:%s" % (copy["id"], wall), "%s:leaf" % copy["openings"][0]["id"],
    }
