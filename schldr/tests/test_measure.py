import math

import pytest

from schldr_lib import document, measure


def room(points, height=2600, **extra):
    data = {"name": "Kamer", "height": height, "points": points}
    data.update(extra)
    return data


def measured(*rooms, **options):
    doc = document.load({"levels": [{"name": "Gelijkvloers", "rooms": list(rooms)}]})
    result = measure.measure_document(doc, **options)
    return doc, {s["ref"].split(":", 1)[-1] if s["kind"] in ("wall", "ceiling", "slope", "floor", "skirting", "moulding") else s["ref"]: s for s in result["surfaces"]}, result


RECT = [[0, 0], [5000, 0], [5000, 4000], [0, 4000]]


def walls(doc):
    return [w["id"] for w in doc["levels"][0]["rooms"][0]["walls"]]


def test_plain_room():
    doc, s, result = measured(room(RECT, has={"floor": True, "moulding": True}))
    ids = walls(doc)
    assert [s["wall:%s" % i]["area_net"] for i in ids] == [13.0, 10.4, 13.0, 10.4]
    assert s["ceiling"]["area_net"] == 20.0
    assert s["floor"]["area_net"] == 20.0
    assert s["skirting"]["length"] == 18.0
    assert s["skirting"]["paint_area"] == 1.26
    assert s["moulding"]["length"] == 18.0
    assert result["rooms"][0]["floor_area"] == 20.0
    assert result["rooms"][0]["wall_area"] == 46.8


def test_clockwise_room_measures_the_same():
    _doc, s, result = measured(room(list(reversed(RECT))))
    assert result["rooms"][0]["wall_area"] == 46.8
    assert s["ceiling"]["area_net"] == 20.0


def test_door_and_window():
    openings = [
        {"wall": "W1", "kind": "door", "offset": 500, "width": 900, "height": 2100,
         "leaf": True, "frame": True},
        {"wall": "W1", "kind": "window", "offset": 2000, "width": 1500, "height": 1200,
         "sill": 900, "reveal": 200, "frame": True},
    ]
    rm = room(RECT, walls=[{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}], openings=openings)
    doc, s, _result = measured(rm)
    wall = s["wall:W1"]
    assert wall["area_gross"] == 13.0
    assert wall["area_openings"] == pytest.approx(0.9 * 2.1 + 1.5 * 1.2)
    # window reveal: two sides and the top, 0.2 deep
    assert wall["area_reveals"] == pytest.approx(0.2 * (2 * 1.2 + 1.5))
    assert wall["area_net"] == pytest.approx(13.0 - 1.89 - 1.8 + 0.78)
    # the doorway is left out of the skirting, the window is not
    assert s["skirting"]["length"] == 17.1
    door, window = doc["levels"][0]["rooms"][0]["openings"]
    assert s["%s:leaf" % door["id"]]["paint_area"] == 3.78
    assert s["%s:leaf" % door["id"]]["count"] == 1
    assert s["%s:frame" % door["id"]]["length"] == 5.1
    assert s["%s:frame" % window["id"]]["length"] == 5.4


def test_small_openings_stay_in_the_bill():
    openings = [
        {"wall": "W1", "kind": "window", "offset": 500, "width": 500, "height": 500, "sill": 1000},
        {"wall": "W1", "kind": "door", "offset": 2000, "width": 900, "height": 2100},
    ]
    rm = room(RECT, walls=[{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}], openings=openings)
    _doc, s, _result = measured(rm, deduct_min_area=1.0)
    assert s["wall:W1"]["area_net"] == pytest.approx(13.0 - 0.25 - 1.89)
    assert s["wall:W1"]["area_billed"] == pytest.approx(13.0 - 1.89)


def test_overlapping_openings_count_once_and_never_more_than_the_wall():
    openings = [
        {"wall": "W1", "kind": "exclusion", "offset": 0, "width": 3000, "height": 2000},
        {"wall": "W1", "kind": "exclusion", "offset": 2000, "width": 3000, "height": 4000},
    ]
    rm = room(RECT, walls=[{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}], openings=openings)
    _doc, s, _result = measured(rm)
    # 0-2 m: 2 high, 2-5 m: the whole wall (2.6)
    assert s["wall:W1"]["area_openings"] == pytest.approx(2 * 2.0 + 3 * 2.6)
    assert s["wall:W1"]["area_net"] == pytest.approx(13.0 - 11.8)


def test_virtual_wall_has_no_surface_and_no_skirting():
    rm = room(RECT, walls=[{"id": "W1", "virtual": True}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}])
    _doc, s, _result = measured(rm)
    assert "wall:W1" not in s
    assert s["skirting"]["length"] == 13.0


def test_wall_with_its_own_heights():
    rm = room(RECT, walls=[{"id": "W1", "h": [2600, 5000]}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}])
    _doc, s, _result = measured(rm)
    assert s["wall:W1"]["area_net"] == 19.0
    assert s["wall:W1"]["height_max"] == 5.0


def attic(slopes, height=2600, points=RECT):
    return room(points, height=height, slopes=slopes,
                walls=[{"id": "W%d" % (i + 1)} for i in range(len(points))])


def test_lean_to_slope():
    # slope from the 5 m wall W1: knee 1 m, 45 degrees -> flat ceiling after 1.6 m
    _doc, s, _result = measured(attic([{"id": "S1", "wall": "W1", "knee": 1000, "pitch": 45}]))
    assert s["wall:W1"]["area_net"] == 5.0                      # knee wall
    assert s["wall:W3"]["area_net"] == 13.0                     # full height
    side = 1.6 * (1.0 + 2.6) / 2 + 2.4 * 2.6                    # trapezium + rectangle
    assert s["wall:W2"]["area_net"] == pytest.approx(side, abs=0.006)
    assert s["wall:W4"]["area_net"] == pytest.approx(side, abs=0.006)
    assert s["slope:S1"]["area_net"] == pytest.approx(5 * 1.6 / math.cos(math.radians(45)), abs=0.006)
    assert s["ceiling"]["area_net"] == 12.0


def test_gable_attic_without_flat_ceiling():
    # two slopes meeting in a ridge at 2 m from each long wall, below the room height
    _doc, s, _result = measured(attic(
        [{"id": "S1", "wall": "W1", "knee": 500, "pitch": 45},
         {"id": "S2", "wall": "W3", "knee": 500, "pitch": 45}], height=4000))
    assert "ceiling" not in s
    each = 5 * 2 / math.cos(math.radians(45))
    assert s["slope:S1"]["area_net"] == pytest.approx(each, abs=0.006)
    assert s["slope:S2"]["area_net"] == pytest.approx(each, abs=0.006)
    gable = 2 * (2 * (0.5 + 2.5) / 2)
    assert s["wall:W2"]["area_net"] == pytest.approx(gable, abs=0.006)
    assert s["wall:W2"]["height_max"] == 2.5


def test_window_under_a_slope_is_cut_off():
    rm = attic([{"id": "S1", "wall": "W1", "knee": 1000, "pitch": 45}])
    # on the side wall W2 (runs away from W1): top line rises from 1.0 m
    rm["openings"] = [{"wall": "W2", "kind": "window", "offset": 0, "width": 1000,
                       "height": 1500, "sill": 500}]
    _doc, s, _result = measured(rm)
    # top of the wall over the window: 1.0 -> 2.0; opening from 0.5 up to it,
    # capped at 2.0: mean visible height 1.0
    assert s["wall:W2"]["area_openings"] == pytest.approx(1.0, abs=0.006)


def test_ceiling_parts_add_up_to_the_floor_in_a_concave_room():
    l_shape = [[0, 0], [6000, 0], [6000, 3000], [3000, 3000], [3000, 6000], [0, 6000]]
    doc = document.load({"levels": [{"rooms": [attic(
        [{"id": "S1", "wall": "W1", "knee": 800, "pitch": 40},
         {"id": "S2", "wall": "W6", "knee": 800, "pitch": 40}], points=l_shape)]}]})
    ceiling = measure.Ceiling(doc["levels"][0]["rooms"][0])
    assert sum(ceiling.parts().values()) == pytest.approx(27.0)
    assert set(ceiling.parts()) == {None, "S1", "S2"}


def test_items():
    rm = room(RECT, items=[
        {"kind": "radiator", "width": 1000, "height": 600, "factor": 2.5, "count": 2},
        {"kind": "custom", "group": "woodwork", "name": "Trapleuning", "length": 3200},
        {"kind": "custom", "name": "Nis", "area": 1.5},
    ])
    doc, s, _result = measured(rm)
    radiator, rail, niche = doc["levels"][0]["rooms"][0]["items"]
    assert s[radiator["id"]]["paint_area"] == 3.0
    assert s[radiator["id"]]["count"] == 2
    assert s[rail["id"]]["group"] == "woodwork"
    assert s[rail["id"]]["length"] == 3.2
    assert s[niche["id"]]["area_net"] == 1.5


def test_assignments_follow_the_defaults_unless_the_room_says_otherwise():
    doc = document.load({
        "defaults": {"assign": {"walls": [{"system": 1, "colour": 7}], "ceilings": [{"system": 2}]}},
        "levels": [{"rooms": [room(RECT, walls=[{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}],
                                   id="R1", assign={"R1:wall:W1": [{"system": 3, "colour": 9}],
                                                    "R1:wall:W2": []})]}],
    })
    surfaces = measure.measure_document(doc)["surfaces"]
    assigned = measure.assignments(doc, surfaces)
    assert assigned["R1:wall:W1"] == [{"system": 3, "colour": 9}]
    assert "R1:wall:W2" not in assigned                       # explicitly unpainted
    assert assigned["R1:wall:W3"] == [{"system": 1, "colour": 7}]
    assert assigned["R1:ceiling"] == [{"system": 2, "colour": False}]
    assert "R1:skirting" not in assigned                      # no default for woodwork


def test_material_needs_per_product_and_colour():
    doc = document.load({
        "defaults": {"assign": {"walls": [{"system": 1, "colour": 7}]}},
        "levels": [{"rooms": [room(RECT, id="R1", walls=[{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}],
                                   assign={"R1:wall:W1": [{"system": 1, "colour": 9}]})]}],
    })
    surfaces = measure.measure_document(doc)["surfaces"]
    systems = {1: {"layers": [
        {"product": 10, "coats": 1, "rate": 8.0, "waste": 0.0, "tinted": False},   # primer
        {"product": 20, "coats": 2, "rate": 10.0, "waste": 10.0, "tinted": True},  # finish
    ]}}
    needs = measure.material_needs(surfaces, measure.assignments(doc, surfaces), systems)
    assert needs[(10, False)] == pytest.approx(46.8 / 8.0)
    assert needs[(20, 9)] == pytest.approx(13.0 * 2 * 1.1 / 10.0)
    assert needs[(20, 7)] == pytest.approx(33.8 * 2 * 1.1 / 10.0)


def test_quantity_follows_the_measure_of_the_system():
    _doc, s, _result = measured(room(RECT))
    assert measure.quantity(s["skirting"], "m") == 18.0
    assert measure.quantity(s["skirting"], "m2") == 1.26
    assert measure.quantity(s["ceiling"], "m2") == 20.0
    assert measure.quantity(s["ceiling"], "piece") == 1.0
