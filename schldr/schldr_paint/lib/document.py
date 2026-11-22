# -*- coding: utf-8 -*-
"""The plan document: the one JSON text a painting project keeps its drawing in.

No Odoo import; mirrored by ``static/src/plan_editor/lib/document.js``.

    {"schema": 1, "units": "mm", "seq": 12,
     "defaults": {"height": 2600, "assign": {"walls": [{"system": 4, "colour": 2}]}},
     "levels": [{"id": "L1", "name": "Gelijkvloers", "elevation": 0, "rooms": [
        {"id": "R2", "name": "Woonkamer", "height": 2600,
         "points": [[0, 0], [5200, 0], [5200, 4100], [0, 4100]],
         "walls": [{"id": "W3"}, {"id": "W4"}, {"id": "W5"}, {"id": "W6"}],
         "slopes": [{"id": "S9", "wall": "W4", "knee": 1000, "pitch": 45}],
         "openings": [{"id": "O7", "wall": "W3", "kind": "door", "offset": 800,
                       "width": 930, "height": 2115, "sill": 0, "reveal": 0,
                       "leaf": true, "frame": true}],
         "items": [{"id": "I8", "kind": "radiator", "width": 1000, "height": 600}],
         "has": {"ceiling": true, "floor": false, "skirting": true, "moulding": false},
         "assign": {"R2:wall:W3": [{"system": 4, "colour": 5}]}}]}]}

All sizes are whole millimetres. ``walls[i]`` is the side from ``points[i]`` to
the next point. Every part has an id of its own (never reused: ``seq`` counts
up), so an assignment stays with its wall when a corner is added or removed.

``assign`` maps a surface (see ``measure.py`` for the references) to the paint
systems on it. A surface that is not in the map follows the project defaults
of its group; an empty list means: not painted.
"""
import copy
import json

SCHEMA = 1

GROUPS = ("walls", "ceilings", "floors", "woodwork", "objects")
OPENING_KINDS = ("door", "window", "passage", "exclusion")
ITEM_KINDS = ("radiator", "custom")

DEFAULT_HEIGHT = 2600
ROOM_HAS = {"ceiling": True, "floor": False, "skirting": True, "moulding": False}


class DocumentError(ValueError):
    """The text is not a plan document this version can read."""


def empty_document():
    return {
        "schema": SCHEMA,
        "units": "mm",
        "seq": 1,
        "defaults": {"height": DEFAULT_HEIGHT, "assign": {}},
        "levels": [{"id": "L1", "name": "Gelijkvloers", "elevation": 0, "rooms": []}],
    }


def _integer(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _entries(value):
    """A clean list of {"system": id, "colour": id or False}."""
    result = []
    for entry in value if isinstance(value, list) else []:
        if not isinstance(entry, dict):
            continue
        system = _integer(entry.get("system"))
        if system > 0:
            result.append({"system": system, "colour": _integer(entry.get("colour")) or False})
    return result


def _assign(value):
    if not isinstance(value, dict):
        return {}
    return {str(key): _entries(entries) for key, entries in value.items()}


def _opening(raw):
    kind = raw.get("kind") if raw.get("kind") in OPENING_KINDS else "door"
    return {
        "id": str(raw.get("id") or ""),
        "wall": str(raw.get("wall") or ""),
        "type": _integer(raw.get("type")) or False,
        "kind": kind,
        "name": raw.get("name") or "",
        "offset": max(_integer(raw.get("offset")), 0),
        "width": max(_integer(raw.get("width")), 0),
        "height": max(_integer(raw.get("height")), 0),
        "sill": max(_integer(raw.get("sill")), 0),
        "reveal": max(_integer(raw.get("reveal")), 0),
        "reveal_sill": bool(raw.get("reveal_sill")),
        "leaf": bool(raw.get("leaf")) and kind == "door",
        "leaf_sides": 1 if _integer(raw.get("leaf_sides"), 2) == 1 else 2,
        "leaf_factor": _number(raw.get("leaf_factor"), 1.0) or 1.0,
        "frame": bool(raw.get("frame")) and kind in ("door", "window"),
        "frame_girth": max(_integer(raw.get("frame_girth"), 150), 0),
        "pair": str(raw.get("pair") or "") or False,
    }


def _item(raw):
    kind = raw.get("kind") if raw.get("kind") in ITEM_KINDS else "custom"
    group = raw.get("group") if raw.get("group") in GROUPS else "objects"
    return {
        "id": str(raw.get("id") or ""),
        "type": _integer(raw.get("type")) or False,
        "kind": kind,
        "group": "objects" if kind == "radiator" else group,
        "name": raw.get("name") or "",
        "wall": str(raw.get("wall") or "") or False,
        "offset": max(_integer(raw.get("offset")), 0),
        "width": max(_integer(raw.get("width")), 0),
        "height": max(_integer(raw.get("height")), 0),
        "length": max(_integer(raw.get("length")), 0),
        "count": max(_integer(raw.get("count"), 1), 1),
        "factor": _number(raw.get("factor"), 1.0) or 1.0,
        # free entry, in m2: an area the drawing cannot give
        "area": max(_number(raw.get("area")), 0.0),
    }


def _room(raw, default_height):
    points = []
    for point in raw.get("points") or []:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append([_integer(point[0]), _integer(point[1])])
    walls = []
    raw_walls = raw.get("walls") or []
    for index in range(len(points)):
        wall = raw_walls[index] if index < len(raw_walls) and isinstance(raw_walls[index], dict) else {}
        heights = wall.get("h")
        if isinstance(heights, (list, tuple)) and len(heights) == 2:
            heights = [max(_integer(heights[0]), 0), max(_integer(heights[1]), 0)]
        else:
            heights = None
        walls.append({
            "id": str(wall.get("id") or ""),
            "name": wall.get("name") or "",
            "virtual": bool(wall.get("virtual")),
            "h": heights,
        })
    has = dict(ROOM_HAS)
    for key in has:
        if key in (raw.get("has") or {}):
            has[key] = bool(raw["has"][key])
    wall_ids = {wall["id"] for wall in walls}
    slopes = []
    for slope in raw.get("slopes") or []:
        if isinstance(slope, dict) and str(slope.get("wall") or "") in wall_ids:
            slopes.append({
                "id": str(slope.get("id") or ""),
                "wall": str(slope["wall"]),
                "knee": max(_integer(slope.get("knee")), 0),
                "pitch": min(max(_number(slope.get("pitch"), 45.0), 1.0), 89.0),
            })
    return {
        "id": str(raw.get("id") or ""),
        "name": raw.get("name") or "",
        "height": max(_integer(raw.get("height"), default_height), 0) or default_height,
        "points": points,
        "walls": walls,
        "slopes": slopes,
        "openings": [
            _opening(o) for o in raw.get("openings") or []
            if isinstance(o, dict) and str(o.get("wall") or "") in wall_ids
        ],
        "items": [_item(i) for i in raw.get("items") or [] if isinstance(i, dict)],
        "has": has,
        "skirting_height": max(_integer(raw.get("skirting_height"), 70), 0),
        "moulding_girth": max(_integer(raw.get("moulding_girth"), 100), 0),
        "assign": _assign(raw.get("assign")),
    }


def migrate(raw):
    """Bring a stored document to the current schema. There is one schema so
    far; a later one adds its step here."""
    schema = _integer(raw.get("schema"), SCHEMA)
    if schema > SCHEMA:
        raise DocumentError("Plan document of a newer version (%s)" % schema)
    return raw


def load(text):
    """The document behind a stored text (or dict), complete and clean: every
    key present, every size a whole number, every part with an id. An empty
    text gives an empty document; a text that is no document raises
    DocumentError."""
    if not text:
        return empty_document()
    if isinstance(text, dict):
        raw = copy.deepcopy(text)
    else:
        try:
            raw = json.loads(text)
        except (TypeError, ValueError):
            raise DocumentError("Plan document is not valid JSON")
    if not isinstance(raw, dict):
        raise DocumentError("Plan document is not an object")
    raw = migrate(raw)

    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    default_height = max(_integer(defaults.get("height"), DEFAULT_HEIGHT), 0) or DEFAULT_HEIGHT
    document = {
        "schema": SCHEMA,
        "units": "mm",
        "seq": max(_integer(raw.get("seq"), 1), 1),
        "defaults": {
            "height": default_height,
            "assign": {
                group: entries for group, entries in _assign(defaults.get("assign")).items()
                if group in GROUPS
            },
        },
        "levels": [],
    }
    for level in raw.get("levels") or []:
        if not isinstance(level, dict):
            continue
        entry = {
            "id": str(level.get("id") or ""),
            "name": level.get("name") or "",
            "elevation": _integer(level.get("elevation")),
            "rooms": [
                _room(room, default_height) for room in level.get("rooms") or []
                if isinstance(room, dict)
            ],
        }
        if isinstance(level.get("background"), dict):
            entry["background"] = level["background"]
        document["levels"].append(entry)
    if not document["levels"]:
        document["levels"] = empty_document()["levels"]
    _complete_ids(document)
    return document


def _complete_ids(document):
    """Give every part without an id (or with one used before) a new one.
    What points at a part of the same room that got a new id -- a slope or an
    opening at its wall, an assignment at its surface -- follows it."""
    seen = set()

    def claim(part, prefix, renamed):
        previous = part["id"]
        if not previous or previous in seen:
            part["id"] = new_id(document, prefix, seen)
            if previous and previous not in renamed:
                renamed[previous] = part["id"]
        seen.add(part["id"])

    for level in document["levels"]:
        claim(level, "L", {})
        for room in level["rooms"]:
            renamed = {}
            claim(room, "R", renamed)
            for wall in room["walls"]:
                claim(wall, "W", renamed)
            for slope in room["slopes"]:
                claim(slope, "S", renamed)
            for opening in room["openings"]:
                claim(opening, "O", renamed)
            for item in room["items"]:
                claim(item, "I", renamed)
            if not renamed:
                continue
            for part in room["slopes"] + room["openings"] + room["items"]:
                if part.get("wall") in renamed:
                    part["wall"] = renamed[part["wall"]]
            room["assign"] = {
                ":".join(renamed.get(token, token) for token in key.split(":")): entries
                for key, entries in room["assign"].items()
            }


def new_id(document, prefix, taken=()):
    while True:
        document["seq"] += 1
        candidate = "%s%d" % (prefix, document["seq"])
        if candidate not in taken:
            return candidate


def dump(document):
    return json.dumps(document, separators=(",", ":"), sort_keys=True)


def iter_rooms(document):
    """(level, room) for every room of the document."""
    for level in document["levels"]:
        for room in level["rooms"]:
            yield level, room
