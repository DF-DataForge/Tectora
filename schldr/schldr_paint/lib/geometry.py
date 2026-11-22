# -*- coding: utf-8 -*-
"""Plane geometry for floor plans. No Odoo import: this module is tested on its
own and mirrored one to one by ``static/src/plan_editor/lib/geometry.js``, so
the editor and the server measure a drawing the same way.

Points are ``(x, y)`` pairs, polygons are lists of points without a repeated
closing point. A line is ``(a, b, c)``: the points where ``a*x + b*y + c == 0``;
its positive side is where that expression is positive.
"""
import math

EPSILON = 1e-9


def signed_area(points):
    """Shoelace area: positive when the points run counter-clockwise in a
    y-up frame."""
    total = 0.0
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def area(points):
    return abs(signed_area(points))


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def perimeter(points, closed=True):
    count = len(points)
    last = count if closed else count - 1
    return sum(distance(points[i], points[(i + 1) % count]) for i in range(last))


def centroid(points):
    """Centre of gravity of the polygon; the mean of its points when it has no
    area."""
    twice = 0.0
    cx = cy = 0.0
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        cross = x1 * y2 - x2 * y1
        twice += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(twice) < EPSILON:
        return (
            sum(p[0] for p in points) / float(count),
            sum(p[1] for p in points) / float(count),
        )
    return (cx / (3.0 * twice), cy / (3.0 * twice))


def bounding_box(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(point, points):
    """Even-odd rule, so it also holds for the pinched polygons clipping a
    concave polygon leaves behind."""
    x, y = point
    inside = False
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def inward_normal(points, index):
    """Unit normal of the side ``index`` (from point ``index`` to the next)
    pointing into the polygon, whichever way its points run."""
    x1, y1 = points[index]
    x2, y2 = points[(index + 1) % len(points)]
    length = math.hypot(x2 - x1, y2 - y1)
    if length < EPSILON:
        return (0.0, 0.0)
    sign = 1.0 if signed_area(points) > 0 else -1.0
    return (-(y2 - y1) / length * sign, (x2 - x1) / length * sign)


def line_value(line, point):
    return line[0] * point[0] + line[1] * point[1] + line[2]


def clip_polygon(points, line):
    """The part of the polygon on the positive side of the line
    (Sutherland-Hodgman). A concave polygon may come back pinched -- parts
    joined by a seam without width -- which leaves its area right."""
    result = []
    count = len(points)
    for index in range(count):
        current = points[index]
        following = points[(index + 1) % count]
        value = line_value(line, current)
        next_value = line_value(line, following)
        if value >= 0:
            result.append(current)
        if (value > 0 and next_value < 0) or (value < 0 and next_value > 0):
            ratio = value / (value - next_value)
            result.append((
                current[0] + (following[0] - current[0]) * ratio,
                current[1] + (following[1] - current[1]) * ratio,
            ))
    return result


def split_polygon(points, line):
    """The polygon cut in two by the line: (positive side, negative side)."""
    opposite = (-line[0], -line[1], -line[2])
    return clip_polygon(points, line), clip_polygon(points, opposite)


def interior_point(points):
    """A point inside the polygon, also when it is concave or pinched: the
    centre of the first corner triangle that lies inside."""
    count = len(points)
    best = None
    for index in range(count):
        a = points[index - 1]
        b = points[index]
        c = points[(index + 1) % count]
        if abs(signed_area([a, b, c])) < EPSILON:
            continue
        candidate = ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)
        if point_in_polygon(candidate, points):
            return candidate
        best = best or candidate
    return best or centroid(points)


def segment_line_crossing(a, b, line):
    """Where the segment a-b crosses the line, as a fraction of the segment
    (strictly between its ends), or None."""
    value_a = line_value(line, a)
    value_b = line_value(line, b)
    if (value_a > EPSILON and value_b < -EPSILON) or (value_a < -EPSILON and value_b > EPSILON):
        return value_a / (value_a - value_b)
    return None


def union_length(intervals):
    """Total length covered by the (start, end) intervals, overlaps once."""
    total = 0.0
    end = None
    for start, stop in sorted(i for i in intervals if i[1] > i[0]):
        if end is None or start > end:
            total += stop - start
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total
