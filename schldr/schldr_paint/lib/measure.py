# -*- coding: utf-8 -*-
"""From a plan document to the surfaces a painter paints, with their sizes.

No Odoo import; mirrored by ``static/src/plan_editor/lib/measure.js``. The
document is in millimetres, everything this module returns in metres.

A surface is one thing that can get a paint system:

    reference          kind       group      measured as
    R2:wall:W3         wall       walls      area (openings out, reveals in)
    R2:ceiling         ceiling    ceilings   area of the flat ceiling
    R2:slope:S9        slope      ceilings   area of the sloped ceiling
    R2:floor           floor      floors     area
    R2:skirting        skirting   woodwork   length (doorways out)
    R2:moulding        moulding   woodwork   length
    O7:frame           frame      woodwork   length around the opening
    O7:leaf            door_leaf  woodwork   one door, both faces as area
    I8                 radiator   objects    pieces
    I8                 custom     (its own)  whatever was entered

The ceiling of a room is flat at the room height, lowered by its slopes: a
slope starts at its wall at knee height and rises into the room at its pitch.
The height at a point is the lowest of the flat ceiling and the slopes that
start behind it, which is what a painter measures in an attic.
"""
import math

from . import geometry
from .document import iter_rooms

MM = 0.001
TOLERANCE = 1e-7

KIND_GROUP = {
    "wall": "walls",
    "ceiling": "ceilings",
    "slope": "ceilings",
    "floor": "floors",
    "skirting": "woodwork",
    "moulding": "woodwork",
    "frame": "woodwork",
    "door_leaf": "woodwork",
    "radiator": "objects",
}

KIND_LABEL = {
    "wall": "Muur",
    "ceiling": "Plafond",
    "slope": "Schuin plafond",
    "floor": "Vloer",
    "skirting": "Plinten",
    "moulding": "Kroonlijst",
    "frame": "Omlijsting",
    "door_leaf": "Deurblad",
    "radiator": "Radiator",
    "custom": "Vrij element",
}

OPENING_LABEL = {
    "door": "Deur",
    "window": "Raam",
    "passage": "Doorgang",
    "exclusion": "Uitsparing",
}


def round2(value):
    """Two decimals, halves up: the same in Python and in JavaScript."""
    return math.floor(value * 100.0 + 0.5 + 1e-9) / 100.0


class Ceiling:
    """The height of a room at any point of its floor."""

    def __init__(self, room):
        self.points = [(x * MM, y * MM) for x, y in room["points"]]
        self.height = room["height"] * MM
        self.slopes = []
        wall_index = {wall["id"]: index for index, wall in enumerate(room["walls"])}
        for slope in room["slopes"]:
            index = wall_index.get(slope["wall"])
            knee = slope["knee"] * MM
            if index is None or knee >= self.height - TOLERANCE:
                continue
            normal = geometry.inward_normal(self.points, index)
            if normal == (0.0, 0.0):
                continue
            origin = self.points[index]
            self.slopes.append({
                "id": slope["id"],
                "knee": knee,
                "rise": math.tan(math.radians(slope["pitch"])),
                "cos": math.cos(math.radians(slope["pitch"])),
                "normal": normal,
                # distance from the wall line = normal . p + offset
                "offset": -(normal[0] * origin[0] + normal[1] * origin[1]),
            })

    def at(self, point):
        """(height, id of the slope that gives it or None) at a point."""
        height, source = self.height, None
        for slope in self.slopes:
            reach = slope["normal"][0] * point[0] + slope["normal"][1] * point[1] + slope["offset"]
            if reach < -TOLERANCE:
                continue  # behind the wall the slope starts at
            value = slope["knee"] + slope["rise"] * max(reach, 0.0)
            if value < height - TOLERANCE:
                height, source = value, slope["id"]
        return height, source

    def lines(self):
        """The lines the ceiling changes along: where a slope starts, where it
        meets the flat ceiling, and where two slopes meet."""
        lines = []
        for slope in self.slopes:
            a, b = slope["normal"]
            lines.append((a, b, slope["offset"]))
            lines.append((a, b, slope["offset"] - (self.height - slope["knee"]) / slope["rise"]))
        for index, first in enumerate(self.slopes):
            for second in self.slopes[index + 1:]:
                a = first["rise"] * first["normal"][0] - second["rise"] * second["normal"][0]
                b = first["rise"] * first["normal"][1] - second["rise"] * second["normal"][1]
                if abs(a) < TOLERANCE and abs(b) < TOLERANCE:
                    continue
                c = (
                    first["knee"] + first["rise"] * first["offset"]
                    - second["knee"] - second["rise"] * second["offset"]
                )
                lines.append((a, b, c))
        return lines

    def parts(self):
        """{slope id or None: plan area}: the floor divided by what hangs
        above it (None: the flat ceiling). The parts add up to the floor."""
        pieces = [self.points]
        for line in self.lines():
            cut = []
            for piece in pieces:
                for half in geometry.split_polygon(piece, line):
                    if len(half) >= 3 and geometry.area(half) > TOLERANCE:
                        cut.append(half)
            pieces = cut
        parts = {}
        for piece in pieces:
            _height, source = self.at(geometry.interior_point(piece))
            parts[source] = parts.get(source, 0.0) + geometry.area(piece)
        return parts


def _wall_profile(room, ceiling, index):
    """The wall as stretches of straight top line: [(start, end, height at
    start, height at end)], distances along the wall in metres."""
    wall = room["walls"][index]
    start = ceiling.points[index]
    end = ceiling.points[(index + 1) % len(ceiling.points)]
    length = geometry.distance(start, end)
    if length < TOLERANCE:
        return []
    if wall["h"]:
        return [(0.0, length, wall["h"][0] * MM, wall["h"][1] * MM)]
    cuts = {0.0, 1.0}
    for line in ceiling.lines():
        ratio = geometry.segment_line_crossing(start, end, line)
        if ratio is not None:
            cuts.add(ratio)
    cuts = sorted(cuts)

    def height_at(ratio):
        point = (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
        # a hair inside the room: on the wall line itself the slope of this
        # wall and those of its neighbours all start
        normal = geometry.inward_normal(ceiling.points, index)
        return ceiling.at((point[0] + normal[0] * 1e-6, point[1] + normal[1] * 1e-6))[0]

    profile = []
    for first, second in zip(cuts, cuts[1:]):
        if second - first < TOLERANCE:
            continue
        # the top is straight within a stretch: two inner points give its ends
        quarter = height_at(first + (second - first) * 0.25)
        three_quarters = height_at(first + (second - first) * 0.75)
        slope = (three_quarters - quarter) * 2.0
        profile.append((
            first * length, second * length,
            quarter - slope * 0.25, three_quarters + slope * 0.25,
        ))
    return profile


def _wall_sizes(profile, openings, deduct_min_area):
    """Areas of a wall with its openings: gross, the openings (overlaps once,
    cut off at the top of the wall), the openings that count for the bill, and
    per opening its own area and the height that is left of it."""
    spans = []
    for opening in openings:
        start = opening["offset"] * MM
        spans.append({
            "opening": opening,
            "start": start,
            "end": start + opening["width"] * MM,
            "bottom": opening["sill"] * MM,
            "top": (opening["sill"] + opening["height"]) * MM,
            "area": 0.0,
            "height": 0.0,
        })

    # cut the wall where an opening starts or ends, and where its top line
    # passes the bottom or top of an opening: within a piece every area is
    # width x height at the middle
    pieces = []
    for start, end, low, high in profile:
        cuts = {start, end}
        for span in spans:
            for edge in (span["start"], span["end"]):
                if start < edge < end:
                    cuts.add(edge)
        cuts = sorted(cuts)
        for first, second in zip(cuts, cuts[1:]):
            first_height = low + (high - low) * (first - start) / (end - start)
            second_height = low + (high - low) * (second - start) / (end - start)
            inner = {first, second}
            for span in spans:
                if span["start"] <= first + TOLERANCE and span["end"] >= second - TOLERANCE:
                    for level in (span["bottom"], span["top"]):
                        if (first_height - level) * (second_height - level) < 0:
                            ratio = (level - first_height) / (second_height - first_height)
                            inner.add(first + (second - first) * ratio)
            inner = sorted(inner)
            for a, b in zip(inner, inner[1:]):
                if b - a < TOLERANCE:
                    continue
                middle = (a + b) / 2.0
                height = first_height + (second_height - first_height) * (middle - first) / (second - first)
                pieces.append((a, b, max(height, 0.0)))

    gross = 0.0
    for a, b, height in pieces:
        gross += (b - a) * height
        for span in spans:
            if span["start"] <= a + TOLERANCE and span["end"] >= b - TOLERANCE:
                visible = max(min(span["top"], height) - span["bottom"], 0.0)
                span["area"] += (b - a) * visible
                span["height"] = max(span["height"], visible)

    def covered(selection):
        total = 0.0
        for a, b, height in pieces:
            intervals = [
                (span["bottom"], min(span["top"], height)) for span in selection
                if span["start"] <= a + TOLERANCE and span["end"] >= b - TOLERANCE
            ]
            total += (b - a) * geometry.union_length(intervals)
        return total

    billed = [span for span in spans if span["area"] >= deduct_min_area - TOLERANCE]
    return {
        "gross": gross,
        "openings": covered(spans),
        "openings_billed": covered(billed),
        "spans": spans,
        "height_max": max([max(low, high) for _s, _e, low, high in profile] or [0.0]),
    }


def _surface(reference, room, level, kind, name, **sizes):
    surface = {
        "ref": reference,
        "room": room["id"],
        "level": level["id"],
        "kind": kind,
        "group": sizes.pop("group", None) or KIND_GROUP.get(kind, "objects"),
        "name": name,
        "area_gross": 0.0,
        "area_openings": 0.0,
        "area_reveals": 0.0,
        "area_net": 0.0,
        "area_billed": 0.0,
        "length": 0.0,
        "count": 0,
        # what the paint has to cover, in m2
        "paint_area": 0.0,
        "height_max": 0.0,
    }
    surface.update(sizes)
    for key in ("area_gross", "area_openings", "area_reveals", "area_net", "area_billed",
                "length", "paint_area", "height_max"):
        surface[key] = round2(surface[key])
    return surface


def measure_room(level, room, deduct_min_area=0.0):
    """The surfaces of one room, in drawing order."""
    if len(room["points"]) < 3:
        return []
    ceiling = Ceiling(room)
    surfaces = []
    prefix = room["id"]
    real_length = 0.0
    doorways = 0.0

    wall_number = 0
    for index, wall in enumerate(room["walls"]):
        if wall["virtual"]:
            continue
        wall_number += 1
        profile = _wall_profile(room, ceiling, index)
        if not profile:
            continue
        length = profile[-1][1]
        openings = [o for o in room["openings"] if o["wall"] == wall["id"]]
        for opening in openings:  # an opening never runs past its wall
            opening["offset"] = min(opening["offset"], int(round(length / MM)))
            opening["width"] = min(opening["width"], int(round(length / MM)) - opening["offset"])
        sizes = _wall_sizes(profile, openings, deduct_min_area)
        reveals = 0.0
        for span in sizes["spans"]:
            opening = span["opening"]
            if opening["kind"] == "exclusion" or not opening["reveal"]:
                continue
            sides = 2.0 * span["height"] + opening["width"] * MM
            if opening["reveal_sill"]:
                sides += opening["width"] * MM
            reveals += opening["reveal"] * MM * sides
        net = max(sizes["gross"] - sizes["openings"], 0.0) + reveals
        billed = max(sizes["gross"] - sizes["openings_billed"], 0.0) + reveals
        surfaces.append(_surface(
            "%s:wall:%s" % (prefix, wall["id"]), room, level, "wall",
            wall["name"] or "%s %d" % (KIND_LABEL["wall"], wall_number),
            area_gross=sizes["gross"], area_openings=sizes["openings"], area_reveals=reveals,
            area_net=net, area_billed=billed, length=length, paint_area=net,
            height_max=sizes["height_max"],
        ))
        real_length += length
        doorways += geometry.union_length([
            (span["start"], span["end"]) for span in sizes["spans"]
            if not span["opening"]["sill"] and span["opening"]["kind"] != "exclusion"
        ])

        for span in sizes["spans"]:
            opening = span["opening"]
            label = opening["name"] or OPENING_LABEL[opening["kind"]]
            width = opening["width"] * MM
            if opening["frame"]:
                around = 2.0 * span["height"] + width
                if opening["kind"] == "window":
                    around += width
                surfaces.append(_surface(
                    "%s:frame" % opening["id"], room, level, "frame",
                    "%s %s" % (KIND_LABEL["frame"], label.lower()),
                    length=around, count=1,
                    paint_area=around * opening["frame_girth"] * MM,
                ))
            if opening["leaf"]:
                faces = width * opening["height"] * MM * opening["leaf_sides"] * opening["leaf_factor"]
                surfaces.append(_surface(
                    "%s:leaf" % opening["id"], room, level, "door_leaf",
                    "%s %s" % (KIND_LABEL["door_leaf"], label.lower()),
                    area_gross=faces, area_net=faces, area_billed=faces,
                    count=1, paint_area=faces,
                ))

    floor = geometry.area(ceiling.points)
    parts = ceiling.parts() if ceiling.slopes else {None: floor}
    if room["has"]["ceiling"]:
        flat = parts.get(None, 0.0)
        if flat > TOLERANCE:
            surfaces.append(_surface(
                "%s:ceiling" % prefix, room, level, "ceiling", KIND_LABEL["ceiling"],
                area_gross=flat, area_net=flat, area_billed=flat, paint_area=flat,
                height_max=ceiling.height,
            ))
        for number, slope in enumerate(ceiling.slopes, 1):
            sloped = parts.get(slope["id"], 0.0) / slope["cos"]
            if sloped > TOLERANCE:
                surfaces.append(_surface(
                    "%s:slope:%s" % (prefix, slope["id"]), room, level, "slope",
                    "%s %d" % (KIND_LABEL["slope"], number),
                    area_gross=sloped, area_net=sloped, area_billed=sloped, paint_area=sloped,
                    height_max=ceiling.height,
                ))
    if room["has"]["floor"]:
        surfaces.append(_surface(
            "%s:floor" % prefix, room, level, "floor", KIND_LABEL["floor"],
            area_gross=floor, area_net=floor, area_billed=floor, paint_area=floor,
        ))
    if room["has"]["skirting"] and real_length - doorways > TOLERANCE:
        run = real_length - doorways
        surfaces.append(_surface(
            "%s:skirting" % prefix, room, level, "skirting", KIND_LABEL["skirting"],
            length=run, paint_area=run * room["skirting_height"] * MM,
        ))
    if room["has"]["moulding"] and real_length > TOLERANCE:
        surfaces.append(_surface(
            "%s:moulding" % prefix, room, level, "moulding", KIND_LABEL["moulding"],
            length=real_length, paint_area=real_length * room["moulding_girth"] * MM,
        ))

    for item in room["items"]:
        count = item["count"]
        if item["kind"] == "radiator":
            faces = item["width"] * MM * item["height"] * MM * item["factor"] * count
            surfaces.append(_surface(
                item["id"], room, level, "radiator", item["name"] or KIND_LABEL["radiator"],
                area_gross=faces, area_net=faces, area_billed=faces, count=count, paint_area=faces,
            ))
        else:
            size = item["area"] or item["width"] * MM * item["height"] * MM * item["factor"]
            size *= count
            surfaces.append(_surface(
                item["id"], room, level, "custom", item["name"] or KIND_LABEL["custom"],
                group=item["group"], area_gross=size, area_net=size, area_billed=size,
                length=item["length"] * MM * count, count=count, paint_area=size,
            ))
    return surfaces


def measure_document(document, deduct_min_area=0.0):
    """Every surface of the document, and per room its floor area, wall
    length and height.

    ``deduct_min_area`` (m2): an opening smaller than this stays in the wall
    area that is billed; the material is always worked out without it.
    """
    surfaces = []
    rooms = []
    for level, room in iter_rooms(document):
        found = measure_room(level, room, deduct_min_area)
        surfaces.extend(found)
        points = [(x * MM, y * MM) for x, y in room["points"]]
        rooms.append({
            "ref": room["id"],
            "level": level["id"],
            "name": room["name"],
            "height": round2(room["height"] * MM),
            "floor_area": round2(geometry.area(points)) if len(points) >= 3 else 0.0,
            "perimeter": round2(geometry.perimeter(points)) if len(points) >= 3 else 0.0,
            "wall_area": round2(sum(s["area_net"] for s in found if s["kind"] == "wall")),
            "ceiling_area": round2(sum(s["area_net"] for s in found if s["group"] == "ceilings")),
        })
    return {"surfaces": surfaces, "rooms": rooms}


def assignments(document, surfaces):
    """{surface reference: [{"system": id, "colour": id or False}]}: what is
    put on each surface. A surface the room says nothing about follows the
    project defaults of its group."""
    explicit = {}
    for _level, room in iter_rooms(document):
        explicit.update(room["assign"])
    defaults = document["defaults"]["assign"]
    result = {}
    for surface in surfaces:
        if surface["ref"] in explicit:
            entries = explicit[surface["ref"]]
        else:
            entries = defaults.get(surface["group"], [])
        if entries:
            result[surface["ref"]] = [dict(entry) for entry in entries]
    return result


def quantity(surface, measure, billed=True):
    """The size of a surface in the unit a paint system is sold in:
    ``m2``, ``m`` or ``piece``."""
    if measure == "m":
        return surface["length"]
    if measure == "piece":
        return float(surface["count"] or 1)
    if surface["kind"] in ("skirting", "moulding", "frame"):
        return surface["paint_area"]
    return surface["area_billed"] if billed else surface["area_net"]


def material_needs(surfaces, assigned, systems):
    """{(product, colour or False): quantity}: what the layers of the assigned
    systems use, added up over the whole document.

    ``systems`` is {id: {"layers": [{"product": id, "coats": 2, "rate": 10.0,
    "dilution": 0.0, "waste": 5.0, "tinted": True}]}}; ``rate`` is how many m2
    one unit of the product (a litre) covers in one coat.
    """
    needs = {}
    for surface in surfaces:
        for entry in assigned.get(surface["ref"], []):
            system = systems.get(entry["system"])
            if not system:
                continue
            for layer in system["layers"]:
                if not layer.get("product") or not layer.get("rate"):
                    continue
                amount = (
                    surface["paint_area"] * layer.get("coats", 1)
                    * (1.0 + layer.get("waste", 0.0) / 100.0)
                    / layer["rate"]
                    / (1.0 + layer.get("dilution", 0.0) / 100.0)
                )
                key = (layer["product"], entry.get("colour") or False if layer.get("tinted") else False)
                needs[key] = needs.get(key, 0.0) + amount
    return needs
