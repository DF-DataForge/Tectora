/** @odoo-module **/

/**
 * Plane geometry for floor plans: the mirror of lib/geometry.py, function by
 * function, so the editor and the server measure a drawing the same way. No
 * Odoo import: this file also runs under node for its tests.
 *
 * Points are [x, y] pairs, polygons are arrays of points without a repeated
 * closing point. A line is [a, b, c]: the points where a*x + b*y + c == 0;
 * its positive side is where that expression is positive.
 */

export const EPSILON = 1e-9;

export function signedArea(points) {
    let total = 0;
    const count = points.length;
    for (let index = 0; index < count; index++) {
        const [x1, y1] = points[index];
        const [x2, y2] = points[(index + 1) % count];
        total += x1 * y2 - x2 * y1;
    }
    return total / 2;
}

export function area(points) {
    return Math.abs(signedArea(points));
}

export function distance(a, b) {
    return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

export function perimeter(points, closed = true) {
    const count = points.length;
    const last = closed ? count : count - 1;
    let total = 0;
    for (let index = 0; index < last; index++) {
        total += distance(points[index], points[(index + 1) % count]);
    }
    return total;
}

export function centroid(points) {
    let twice = 0;
    let cx = 0;
    let cy = 0;
    const count = points.length;
    for (let index = 0; index < count; index++) {
        const [x1, y1] = points[index];
        const [x2, y2] = points[(index + 1) % count];
        const cross = x1 * y2 - x2 * y1;
        twice += cross;
        cx += (x1 + x2) * cross;
        cy += (y1 + y2) * cross;
    }
    if (Math.abs(twice) < EPSILON) {
        return [
            points.reduce((sum, p) => sum + p[0], 0) / count,
            points.reduce((sum, p) => sum + p[1], 0) / count,
        ];
    }
    return [cx / (3 * twice), cy / (3 * twice)];
}

export function boundingBox(points) {
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function pointInPolygon(point, points) {
    const [x, y] = point;
    let inside = false;
    const count = points.length;
    for (let index = 0; index < count; index++) {
        const [x1, y1] = points[index];
        const [x2, y2] = points[(index + 1) % count];
        if (y1 > y !== y2 > y) {
            if (x < x1 + ((y - y1) * (x2 - x1)) / (y2 - y1)) {
                inside = !inside;
            }
        }
    }
    return inside;
}

export function inwardNormal(points, index) {
    const [x1, y1] = points[index];
    const [x2, y2] = points[(index + 1) % points.length];
    const length = Math.hypot(x2 - x1, y2 - y1);
    if (length < EPSILON) {
        return [0, 0];
    }
    const sign = signedArea(points) > 0 ? 1 : -1;
    return [(-(y2 - y1) / length) * sign, ((x2 - x1) / length) * sign];
}

export function lineValue(line, point) {
    return line[0] * point[0] + line[1] * point[1] + line[2];
}

export function clipPolygon(points, line) {
    const result = [];
    const count = points.length;
    for (let index = 0; index < count; index++) {
        const current = points[index];
        const following = points[(index + 1) % count];
        const value = lineValue(line, current);
        const nextValue = lineValue(line, following);
        if (value >= 0) {
            result.push(current);
        }
        if ((value > 0 && nextValue < 0) || (value < 0 && nextValue > 0)) {
            const ratio = value / (value - nextValue);
            result.push([
                current[0] + (following[0] - current[0]) * ratio,
                current[1] + (following[1] - current[1]) * ratio,
            ]);
        }
    }
    return result;
}

export function splitPolygon(points, line) {
    return [clipPolygon(points, line), clipPolygon(points, [-line[0], -line[1], -line[2]])];
}

export function interiorPoint(points) {
    const count = points.length;
    let best = null;
    for (let index = 0; index < count; index++) {
        const a = points[(index - 1 + count) % count];
        const b = points[index];
        const c = points[(index + 1) % count];
        if (Math.abs(signedArea([a, b, c])) < EPSILON) {
            continue;
        }
        const candidate = [(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3];
        if (pointInPolygon(candidate, points)) {
            return candidate;
        }
        best = best || candidate;
    }
    return best || centroid(points);
}

export function segmentLineCrossing(a, b, line) {
    const valueA = lineValue(line, a);
    const valueB = lineValue(line, b);
    if ((valueA > EPSILON && valueB < -EPSILON) || (valueA < -EPSILON && valueB > EPSILON)) {
        return valueA / (valueA - valueB);
    }
    return null;
}

export function unionLength(intervals) {
    let total = 0;
    let end = null;
    const sorted = intervals
        .filter((interval) => interval[1] > interval[0])
        .sort((first, second) => first[0] - second[0] || first[1] - second[1]);
    for (const [start, stop] of sorted) {
        if (end === null || start > end) {
            total += stop - start;
            end = stop;
        } else if (stop > end) {
            total += stop - end;
            end = stop;
        }
    }
    return total;
}

// ---- only the editor needs these -------------------------------------------

/** Distance from a point to the segment a-b, and how far along it (0..1). */
export function nearestOnSegment(point, a, b) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const lengthSquared = dx * dx + dy * dy;
    let ratio = 0;
    if (lengthSquared > EPSILON) {
        ratio = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSquared;
        ratio = Math.max(0, Math.min(1, ratio));
    }
    const nearest = [a[0] + dx * ratio, a[1] + dy * ratio];
    return { distance: distance(point, nearest), ratio, point: nearest };
}
