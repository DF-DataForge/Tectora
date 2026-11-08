/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { RoofProductPickerDialog } from "./product_picker_dialog";
import { RoofEdgeLengthDialog } from "./edge_length_dialog";
import {
    Component,
    onMounted,
    onWillUnmount,
    proxy,
    signal,
    useProps,
} from "@odoo/owl";

// 50 px per meter — same default as the legacy standalone canvas.
const DEFAULT_SCALE_M_PER_PX = 0.02;
const DEFAULT_WORLD = { w: 1400, h: 900 };
const CLOSE_SNAP_PX = 12;
const MIN_RECT_PX = 6;
// Screen-pixel drag distance before a whole shape starts moving; guards
// against accidentally displacing a section while clicking around.
const MOVE_START_SCREEN_PX = 8;
// Candidate grid spacings in meters; the smallest one that renders at a
// readable on-screen distance is used, minor lines every step, major every 5.
const GRID_STEPS_M = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
const GRID_MIN_SCREEN_PX = 30;
const GRID_MAJOR_EVERY = 5;
// Edges shorter than this on screen don't get a length box (unreadable).
const EDGE_LABEL_MIN_SCREEN_PX = 34;
const DEFAULT_CANVAS_HEIGHT = 620;
const WHEEL_ZOOM_STEP = 1.12;
// Default real-world size (meters) of roof objects added via right-click.
const OBJECT_DEFAULT_SIZE_M = { chimney: 0.8, skylight: 1.2 };
// Circles are stored as regular polygons so measurements and the server-side
// sync keep working; 48 points keeps area/perimeter within ~0.5% of exact.
const CIRCLE_POINTS = 48;
// Ctrl-selected targets waiting for products.
// How much of a dakobject the category icon is allowed to fill.
const ICON_FILL_RATIO = 0.7;
const MULTI_SELECT_STROKE = "#6c3fa4";
const MULTI_SELECT_FILL = "rgba(108, 63, 164, 0.92)";

function circlePoints(cx, cy, radius) {
    const points = [];
    for (let i = 0; i < CIRCLE_POINTS; i++) {
        const angle = (i / CIRCLE_POINTS) * Math.PI * 2;
        points.push([
            Math.round((cx + radius * Math.cos(angle)) * 100) / 100,
            Math.round((cy + radius * Math.sin(angle)) * 100) / 100,
        ]);
    }
    return points;
}
// The one colour the drawing marks with: the selected side (or surface) and
// the parts a hovered quotation line comes from.
const HIGHLIGHT = "#f59e0b";

const KIND_NAMES = { section: "Sectie", chimney: "Schoorsteen", skylight: "Koepel", seam: "Naad" };

const KIND_STYLES = {
    section: { fill: "rgba(10, 116, 131, 0.28)", stroke: "#0a7483", label: "" },
    chimney: { fill: "rgba(217, 119, 6, 0.35)", stroke: "#b45309", label: "Schoorsteen" },
    skylight: { fill: "rgba(37, 99, 235, 0.30)", stroke: "#1d4ed8", label: "Koepel" },
    // A seam (naad) is an open dotted line between two roof surfaces.
    seam: { fill: "rgba(0, 0, 0, 0)", stroke: "#374151", label: "Naad", dashed: true },
};

// How close (screen px) a click must come to a seam to select it.
const SEAM_HIT_SCREEN_PX = 8;

function isSeam(shape) {
    return (shape && shape.kind) === "seam";
}

// Distance from a point to an open polyline (world units).
function distanceToPolyline([px, py], points) {
    let best = Infinity;
    for (let i = 0; i < points.length - 1; i++) {
        const [ax, ay] = points[i];
        const [bx, by] = points[i + 1];
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSq = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lengthSq));
        best = Math.min(best, Math.hypot(px - (ax + dx * t), py - (ay + dy * t)));
    }
    return best;
}

// Intersection of segments a-b and c-d: {point, t (along a-b), u (along c-d)}
// or null when they do not cross.
function segmentIntersection(a, b, c, d) {
    const r = [b[0] - a[0], b[1] - a[1]];
    const s = [d[0] - c[0], d[1] - c[1]];
    const denom = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(denom) < 1e-9) {
        return null;
    }
    const q = [c[0] - a[0], c[1] - a[1]];
    const t = (q[0] * s[1] - q[1] * s[0]) / denom;
    const u = (q[0] * r[1] - q[1] * r[0]) / denom;
    const eps = 1e-6;
    if (t < -eps || t > 1 + eps || u < -eps || u > 1 + eps) {
        return null;
    }
    return { point: [a[0] + r[0] * t, a[1] + r[1] * t], t, u };
}

// Split a polygon along an open polyline (a seam) into the two surfaces on
// either side. Seam ends that stop inside the polygon are extended along
// their last segment to the outline, so a seam drawn "roughly across" splits
// as well. Returns [polygonA, polygonB] or null when the seam does not cross
// the polygon cleanly (fewer than two crossings, or a degenerate part).
function splitPolygonByPolyline(polygon, polyline, extendEnds = true) {
    const n = polygon.length;
    if (n < 3 || polyline.length < 2) {
        return null;
    }
    const box = boundingBox(polygon);
    const reach = (box.w + box.h) * 4 + 10;
    const line = polyline.map((p) => [...p]);
    const extend = (from, to) => {
        // Point far beyond `to`, coming from `from`.
        const dx = to[0] - from[0];
        const dy = to[1] - from[1];
        const length = Math.hypot(dx, dy) || 1;
        return [to[0] + (dx / length) * reach, to[1] + (dy / length) * reach];
    };
    if (extendEnds && pointInPolygon(line[0], polygon)) {
        line[0] = extend(line[1], line[0]);
    }
    if (extendEnds && pointInPolygon(line[line.length - 1], polygon)) {
        line[line.length - 1] = extend(line[line.length - 2], line[line.length - 1]);
    }
    const crossings = [];
    for (let k = 0; k < line.length - 1; k++) {
        for (let i = 0; i < n; i++) {
            const hit = segmentIntersection(line[k], line[k + 1], polygon[i], polygon[(i + 1) % n]);
            if (hit) {
                crossings.push({ seg: k, t: hit.t, edge: i, u: hit.u, point: hit.point });
            }
        }
    }
    if (crossings.length < 2) {
        return null;
    }
    crossings.sort((a, b) => a.seg - b.seg || a.t - b.t);
    const entry = crossings[0];
    const exit = crossings[crossings.length - 1];
    if (entry.seg === exit.seg && Math.abs(entry.t - exit.t) < 1e-6) {
        return null;
    }
    // Seam vertices strictly between the two crossings.
    const inside = [];
    for (let k = entry.seg + 1; k <= exit.seg; k++) {
        inside.push(line[k]);
    }
    const walk = (fromEdge, toEdge, fromU, toU) => {
        // Polygon vertices after the crossing on fromEdge up to and including
        // the start of the crossing on toEdge, going forward.
        let count = (toEdge - fromEdge + n) % n;
        if (fromEdge === toEdge && toU < fromU) {
            count = n;
        }
        const out = [];
        for (let step = 1; step <= count; step++) {
            out.push(polygon[(fromEdge + step) % n]);
        }
        return out;
    };
    const partA = [entry.point, ...walk(entry.edge, exit.edge, entry.u, exit.u), exit.point, ...[...inside].reverse()];
    const partB = [exit.point, ...walk(exit.edge, entry.edge, exit.u, entry.u), entry.point, ...inside];
    const total = polygonArea(polygon);
    const clean = (part) => {
        const out = [];
        for (const p of part) {
            const last = out[out.length - 1];
            if (!last || Math.hypot(p[0] - last[0], p[1] - last[1]) > 0.5) {
                out.push(p);
            }
        }
        if (out.length > 2) {
            const first = out[0];
            const last = out[out.length - 1];
            if (Math.hypot(first[0] - last[0], first[1] - last[1]) <= 0.5) {
                out.pop();
            }
        }
        return out;
    };
    const a = clean(partA);
    const b = clean(partB);
    if (a.length < 3 || b.length < 3) {
        return null;
    }
    if (polygonArea(a) < total * 0.01 || polygonArea(b) < total * 0.01) {
        return null;
    }
    return [a, b];
}

const SEAM_JOIN_PX = 1.5;

// Distance from point p to segment a-b.
function distanceToSegment(p, a, b) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const length2 = dx * dx + dy * dy;
    const t = length2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2)) : 0;
    return Math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t));
}

function onPolyline(p, line) {
    for (let i = 0; i < line.length - 1; i++) {
        if (distanceToSegment(p, line[i], line[i + 1]) <= SEAM_JOIN_PX) {
            return true;
        }
    }
    return false;
}

// A seam as it divides ``polygon``: an end left loose inside the surface is
// drawn on to the first outline or other seam it meets; an end on another
// seam stays there (a T-joint: the seam only divides the sheet on its side).
function effectiveSeam(seam, polygon, others) {
    const line = seam.map((p) => [...p]);
    const box = boundingBox(polygon);
    const reach = (box.w + box.h) * 4 + 10;
    const segments = [];
    for (let i = 0; i < polygon.length; i++) {
        segments.push([polygon[i], polygon[(i + 1) % polygon.length]]);
    }
    for (const other of others) {
        for (let i = 0; i < other.length - 1; i++) {
            segments.push([other[i], other[i + 1]]);
        }
    }
    const extendEnd = (from, to) => {
        const dx = to[0] - from[0];
        const dy = to[1] - from[1];
        const length = Math.hypot(dx, dy) || 1;
        const far = [to[0] + (dx / length) * reach, to[1] + (dy / length) * reach];
        let best = null;
        for (const [a, b] of segments) {
            const hit = segmentIntersection(to, far, a, b);
            if (hit && hit.t > 1e-6 && (!best || hit.t < best.t)) {
                best = hit;
            }
        }
        return best ? best.point : to;
    };
    // An end on the outline (a corner too: the inside test is unreliable
    // there) or on another seam is not loose.
    const outline = [...polygon, polygon[0]];
    const loose = (end) =>
        pointInPolygon(end, polygon) &&
        !onPolyline(end, outline) &&
        !others.some((other) => onPolyline(end, other));
    if (line.length >= 2 && loose(line[0])) {
        line[0] = extendEnd(line[1], line[0]);
    }
    const last = line.length - 1;
    if (line.length >= 2 && loose(line[last])) {
        line[last] = extendEnd(line[last - 1], line[last]);
    }
    // Every end runs on a little: an end on another seam or on the outline
    // (stored rounded, a hair beside it) then surely crosses it.
    const overshoot = (from, to) => {
        const dx = to[0] - from[0];
        const dy = to[1] - from[1];
        const length = Math.hypot(dx, dy) || 1;
        return [to[0] + (dx / length) * SEAM_JOIN_PX * 2, to[1] + (dy / length) * SEAM_JOIN_PX * 2];
    };
    if (line.length >= 2) {
        line[0] = overshoot(line[1], line[0]);
        line[last] = overshoot(line[last - 1], line[last]);
    }
    return line;
}

// A polygon cut by every seam crossing it: the EPDM sheets of a surface.
// A seam may end on another seam, dividing only the sheet on its side.
function splitBySeams(polygon, seams) {
    const lines = seams.map((seam, i) => effectiveSeam(seam, polygon, seams.filter((_, j) => j !== i)));
    let pieces = [polygon];
    // A seam ending on another one only cuts once that one has: repeat
    // until no seam cuts anything more.
    let pending = [...lines];
    let progress = true;
    while (pending.length && progress) {
        progress = false;
        const left = [];
        for (const line of pending) {
            let cut = false;
            const next = [];
            for (const piece of pieces) {
                const parts = splitPolygonByPolyline(piece, line, false);
                if (parts) {
                    cut = true;
                    next.push(...parts);
                } else {
                    next.push(piece);
                }
            }
            pieces = next;
            if (cut) {
                progress = true;
            } else {
                left.push(line);
            }
        }
        pending = left;
    }
    return pieces;
}

// Area centroid of a polygon (falls back to the bounding box centre).
function polygonCentroid(points) {
    let area = 0;
    let cx = 0;
    let cy = 0;
    for (let i = 0; i < points.length; i++) {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % points.length];
        const cross = x1 * y2 - x2 * y1;
        area += cross;
        cx += (x1 + x2) * cross;
        cy += (y1 + y2) * cross;
    }
    if (Math.abs(area) < 1e-9) {
        const box = boundingBox(points);
        return [box.x + box.w / 2, box.y + box.h / 2];
    }
    return [cx / (3 * area), cy / (3 * area)];
}

const MERGE_TOLERANCE_PX = 0.6;

function samePoint(a, b) {
    return Math.hypot(a[0] - b[0], a[1] - b[1]) <= MERGE_TOLERANCE_PX;
}

function pointOnSegment(p, a, b) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    if (length < 1e-9) {
        return samePoint(p, a);
    }
    const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (length * length);
    if (t <= 1e-6 || t >= 1 - 1e-6) {
        return false;
    }
    return Math.abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length <= MERGE_TOLERANCE_PX;
}

// ``polygon`` with every point of ``others`` that lies on one of its sides
// inserted as a vertex, so shared sides match vertex for vertex.
function withVerticesOf(polygon, others) {
    const out = [];
    for (let i = 0; i < polygon.length; i++) {
        const a = polygon[i];
        const b = polygon[(i + 1) % polygon.length];
        out.push(a);
        const between = others
            .filter((p) => pointOnSegment(p, a, b))
            .sort(
                (p, q) =>
                    Math.hypot(p[0] - a[0], p[1] - a[1]) - Math.hypot(q[0] - a[0], q[1] - a[1])
            );
        for (const p of between) {
            if (!samePoint(p, out[out.length - 1])) {
                out.push(p);
            }
        }
    }
    return out;
}

// The union of two polygons that share (part of) their outline, e.g. the
// two halves of a section split along a seam; null when they do not touch
// or the result is not one closed outline.
function mergePolygons(a, b) {
    const pa = withVerticesOf(a, b);
    const pb = withVerticesOf(b, a);
    const edges = (poly) => poly.map((p, i) => [p, poly[(i + 1) % poly.length]]);
    const ea = edges(pa);
    const eb = edges(pb);
    const shared = (edge, list) => list.some(([p, q]) => samePoint(edge[0], q) && samePoint(edge[1], p));
    const keepA = ea.filter((edge) => !shared(edge, eb));
    const keepB = eb.filter((edge) => !shared(edge, ea));
    if (keepA.length === ea.length) {
        return null; // nothing in common
    }
    const remaining = [...keepA, ...keepB];
    const result = [remaining[0][0]];
    let current = remaining.shift();
    while (remaining.length) {
        const index = remaining.findIndex(([p]) => samePoint(p, current[1]));
        if (index < 0) {
            return null;
        }
        current = remaining.splice(index, 1)[0];
        result.push(current[0]);
    }
    if (!samePoint(current[1], result[0])) {
        return null;
    }
    // Points on a straight side are no corners.
    const clean = result.filter((p, i) => {
        const prev = result[(i - 1 + result.length) % result.length];
        const next = result[(i + 1) % result.length];
        const cross = (p[0] - prev[0]) * (next[1] - p[1]) - (p[1] - prev[1]) * (next[0] - p[0]);
        const scale = Math.hypot(p[0] - prev[0], p[1] - prev[1]) * Math.hypot(next[0] - p[0], next[1] - p[1]) || 1;
        return Math.abs(cross) / scale > 1e-3;
    });
    return clean.length >= 3 ? clean : null;
}

// Point halfway along an open polyline, for its label.
function polylineMidpoint(points) {
    const total = polygonPerimeter(points, false);
    let remaining = total / 2;
    for (let i = 0; i < points.length - 1; i++) {
        const [ax, ay] = points[i];
        const [bx, by] = points[i + 1];
        const length = Math.hypot(bx - ax, by - ay);
        if (remaining <= length || i === points.length - 2) {
            const t = length ? Math.min(1, remaining / length) : 0;
            return [ax + (bx - ax) * t, ay + (by - ay) * t];
        }
        remaining -= length;
    }
    return points[0];
}

function polygonSignedArea(points) {
    let total = 0;
    const n = points.length;
    for (let i = 0; i < n; i++) {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % n];
        total += x1 * y2 - x2 * y1;
    }
    return total / 2;
}

function polygonArea(points) {
    return Math.abs(polygonSignedArea(points));
}

// True when vertex i is a reflex (inner) corner of the polygon.
function isInnerCorner(points, i) {
    const n = points.length;
    const [ax, ay] = points[(i - 1 + n) % n];
    const [px, py] = points[i];
    const [bx, by] = points[(i + 1) % n];
    const cross = (px - ax) * (by - py) - (py - ay) * (bx - px);
    if (cross === 0) {
        return false; // collinear: treat as outer
    }
    const orientation = Math.sign(polygonSignedArea(points)) || 1;
    return Math.sign(cross) !== orientation;
}

function polygonPerimeter(points, closed = true) {
    let total = 0;
    const n = points.length;
    const last = closed ? n : n - 1;
    for (let i = 0; i < last; i++) {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % n];
        total += Math.hypot(x2 - x1, y2 - y1);
    }
    return total;
}

// Give side `index` of the polygon exactly `targetPx` length by sliding its
// corner(s) along the side, so the side keeps its direction. `anchor` says
// which end stays put: "start", "end" or "center" (both move half).
// Returns a new point list; the polygon stays closed, and the two
// neighbouring sides stretch along with the moved corner.
function resizeEdgePoints(points, index, targetPx, anchor = "start") {
    const n = points.length;
    const next = (index + 1) % n;
    const [x1, y1] = points[index];
    const [x2, y2] = points[next];
    const lengthPx = Math.hypot(x2 - x1, y2 - y1);
    if (!(lengthPx > 0) || !(targetPx > 0)) {
        return points.map((p) => [...p]);
    }
    const ux = (x2 - x1) / lengthPx;
    const uy = (y2 - y1) / lengthPx;
    const delta = targetPx - lengthPx;
    const round = (value) => Math.round(value * 100) / 100;
    const result = points.map((p) => [...p]);
    if (anchor === "end") {
        result[index] = [round(x1 - ux * delta), round(y1 - uy * delta)];
    } else if (anchor === "center") {
        result[index] = [round(x1 - (ux * delta) / 2), round(y1 - (uy * delta) / 2)];
        result[next] = [round(x2 + (ux * delta) / 2), round(y2 + (uy * delta) / 2)];
    } else {
        result[next] = [round(x2 + ux * delta), round(y2 + uy * delta)];
    }
    return result;
}

function boundingBox(points) {
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    return {
        x: minX,
        y: minY,
        w: Math.max(...xs) - minX,
        h: Math.max(...ys) - minY,
    };
}

function pointInPolygon([px, py], points) {
    let inside = false;
    const n = points.length;
    for (let i = 0, j = n - 1; i < n; j = i++) {
        const [xi, yi] = points[i];
        const [xj, yj] = points[j];
        if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
            inside = !inside;
        }
    }
    return inside;
}

function makeId() {
    return "shape-" + Math.random().toString(36).slice(2, 10) + "-" + Date.now().toString(36);
}

function lineIntersection(point1, dir1, point2, dir2) {
    const cross = dir1[0] * dir2[1] - dir1[1] * dir2[0];
    if (Math.abs(cross) < 1e-9) {
        return null; // parallel
    }
    const t =
        ((point2[0] - point1[0]) * dir2[1] - (point2[1] - point1[1]) * dir2[0]) /
        cross;
    return [point1[0] + dir1[0] * t, point1[1] + dir1[1] * t];
}

// Inset a polygon with a per-edge distance (canvas px): every edge is moved
// inward by its own width, new vertices are the intersections of adjacent
// offset edges. Returns null when the widths degenerate the polygon.
function insetPolygon(points, widths) {
    const n = points.length;
    if (n < 3) {
        return null;
    }
    const offsetEdges = [];
    for (let i = 0; i < n; i++) {
        const [ax, ay] = points[i];
        const [bx, by] = points[(i + 1) % n];
        const dx = bx - ax;
        const dy = by - ay;
        const length = Math.hypot(dx, dy) || 1;
        let nx = -dy / length;
        let ny = dx / length;
        const probe = [(ax + bx) / 2 + nx * 0.5, (ay + by) / 2 + ny * 0.5];
        if (!pointInPolygon(probe, points)) {
            nx = -nx;
            ny = -ny;
        }
        const width = widths[i] || 0;
        offsetEdges.push({
            p: [ax + nx * width, ay + ny * width],
            d: [dx, dy],
        });
    }
    const inner = [];
    for (let i = 0; i < n; i++) {
        const previous = offsetEdges[(i - 1 + n) % n];
        const current = offsetEdges[i];
        const vertex =
            lineIntersection(previous.p, previous.d, current.p, current.d) ||
            [...current.p];
        if (!isFinite(vertex[0]) || !isFinite(vertex[1])) {
            return null;
        }
        inner.push(vertex);
    }
    // Degenerate widths flip the polygon inside-out: the orientation of the
    // result must match the original.
    const signedInner = polygonSignedArea(inner);
    const signedOuter = polygonSignedArea(points);
    if (
        !isFinite(signedInner) ||
        Math.sign(signedInner) !== Math.sign(signedOuter) ||
        Math.abs(signedInner) > Math.abs(signedOuter)
    ) {
        return null;
    }
    return inner;
}

export class RoofCanvasField extends Component {
    static template = "tectora_roof.RoofCanvasField";
    props = useProps(standardFieldProps);

    setup() {
        this.canvasRef = signal.ref();
        this.wrapperRef = signal.ref();
        this.mainRef = signal.ref();
        this.toolbarRef = signal.ref();
        this.statusRef = signal.ref();
        this.bgMenuRef = signal.ref();
        this.bgFileRef = signal.ref();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = proxy({
            tool: "select",
            showBackground: true,
            backgroundOpacity: 0.9,
            showGrid: true,
            gridStep: 1,
            selectedId: null,
            status: "",
            contextMenu: null, // {x, y (px in wrapper), worldPoint}
            panel: null, // product card for the selected shape
            // The element of the selected shape the side panel describes: its
            // surface (or the whole dakobject / naad) or one side.
            focus: null, // {type: "surface"|"edge", shapeId, kind, edgeIndex, hit}
            // Other sides of the focused shape ticked to get the same
            // description (edge indexes).
            copyTargets: [],
            // Tekenmodus: the plan, its toolbar and the side panel fixed on
            // the screen under Odoo's menu bar, to draw, assign products and
            // describe without the form scrolling away.
            fullscreen: false,
            bgMenu: false, // the background menu (satellite, plan) is open
            bgBusy: false, // a background fetch/upload is running
            // Ctrl-clicked sides, surfaces or corners waiting for Ctrl to be
            // released; they then all get the same products at once.
            multiSelect: [],
            // The quotation as the drawing builds it (tectora_get_quote_preview),
            // shown beside the drawing; each line with parts of the drawing has
            // its parts highlighted on the drawing while hovered.
            quote: null,
            quoteLoading: false,
            quoteOpen: true,
            quoteHover: null, // key of the line hovered in the panel
        });
        this.world = { ...DEFAULT_WORLD };
        this.view = { zoom: 1, x: 0, y: 0 };
        this.backgroundImage = null;
        this.drag = null; // {mode: 'move'|'rect'|'pan', ...}
        this.draftPolygon = null; // [[x, y], ...]
        this.draftCursor = null; // where the side being drawn ends (pointer)
        this._rawCache = undefined;
        this._staleRaw = null;
        this._shapes = [];
        this.labelHits = []; // clickable measurement boxes, in world coordinates
        this.iconImages = {}; // product category id -> loaded icon (or null)
        this._iconRaw = undefined;
        this._iconMap = {};

        this.onWindowResize = () => this.resizeCanvas();
        // On window rather than on the canvas: the picker has to open when Ctrl
        // is released even if the focus moved to the panel in between.
        this.onWindowKeyUp = (ev) => {
            if (ev.key === "Control" || ev.key === "Meta") {
                this.flushMultiSelect();
            }
        };
        // A click anywhere outside the background menu closes it.
        this.onWindowPointerDown = (ev) => {
            if (this.state.bgMenu && this.bgMenuRef() && !this.bgMenuRef().contains(ev.target)) {
                this.state.bgMenu = false;
            }
        };
        this._destroyed = false;
        this._autoSyncTimer = null;

        onMounted(() => {
            this.resizeCanvas();
            this.loadQuote();
            this.loadBackground();
            window.addEventListener("resize", this.onWindowResize);
            window.addEventListener("keyup", this.onWindowKeyUp);
            window.addEventListener("pointerdown", this.onWindowPointerDown, true);
            // The main column changes size when the side panel opens or the
            // form gets narrower; follow it, not only the window.
            if (window.ResizeObserver && this.mainRef()) {
                this._resizeObserver = new ResizeObserver(() => {
                    if (this._destroyed) {
                        return;
                    }
                    const canvas = this.canvasRef();
                    const main = this.mainRef();
                    if (canvas && main && Math.abs(canvas.width - main.clientWidth) > 1) {
                        this.resizeCanvas();
                    }
                });
                this._resizeObserver.observe(this.mainRef());
            }
        });
        onWillUnmount(() => {
            this._destroyed = true;
            clearTimeout(this._autoSyncTimer);
            clearTimeout(this._quoteTimer);
            if (this._resizeObserver) {
                this._resizeObserver.disconnect();
            }
            window.removeEventListener("resize", this.onWindowResize);
            window.removeEventListener("keyup", this.onWindowKeyUp);
            window.removeEventListener("pointerdown", this.onWindowPointerDown, true);
        });
    }

    // ------------------------------------------------------------- record I/O
    get shapes() {
        const raw = this.props.record.data[this.props.name] || "";
        if (raw === this._rawCache) {
            this._staleRaw = null;
        } else if (raw !== this._staleRaw) {
            this._rawCache = raw;
            try {
                const parsed = JSON.parse(raw || "{}");
                this._shapes = Array.isArray(parsed.shapes) ? parsed.shapes : [];
            } catch {
                this._shapes = [];
            }
        }
        return this._shapes;
    }

    commit() {
        const raw = JSON.stringify({ shapes: this._shapes });
        // record.update() applies asynchronously: until it lands, the record
        // still holds the previous drawing, which must not be re-read over
        // the committed shapes (the snapshot below would show the old ones).
        this._staleRaw = this.props.record.data[this.props.name] || "";
        this._rawCache = raw;
        const values = { [this.props.name]: raw };
        const snapshot = this.exportSnapshot();
        if (snapshot && "canvas_snapshot" in this.props.record.data) {
            values.canvas_snapshot = snapshot;
        }
        this.props.record.update(values);
        this.draw();
        this.scheduleAutoSync();
    }

    scheduleAutoSync() {
        // Debounced: quick successive edits sync once, and a sync never
        // starts in the same tick as a user action (avoids racing the form
        // controller's own save when e.g. the pager is clicked).
        clearTimeout(this._autoSyncTimer);
        this._autoSyncTimer = setTimeout(() => this.autoSyncFromCanvas(), 400);
    }

    async autoSyncFromCanvas() {
        // Keep the sections/objects in sync with the drawing without a manual
        // 'Meting bijwerken uit tekening' click. Only for already-saved
        // projects: on a brand-new record the drawing stays local until the
        // user saves it for the first time.
        const record = this.props.record;
        if (this._destroyed || !record.resId) {
            return;
        }
        if (this._syncing) {
            this._syncPending = true;
            return;
        }
        this._syncing = true;
        try {
            if (!(await record.save())) {
                return;
            }
            if (this._destroyed) {
                return;
            }
            await this.orm.call(
                "tectora.roof.project", "action_sync_from_canvas",
                [record.resId], { context: { tectora_quiet_sync: true } }
            );
            await record.load();
            this.draw();
            this.refreshPanel();
        } catch (error) {
            console.warn("Roof canvas auto-sync failed", error);
        } finally {
            this._syncing = false;
            if (this._syncPending) {
                this._syncPending = false;
                this.autoSyncFromCanvas();
            }
        }
    }

    exportSnapshot() {
        // Fitted PNG of the whole drawing, stored on the record and used on
        // the measurement sheet PDF attached to quotations.
        const canvas = this.canvasRef();
        if (!canvas) {
            return null;
        }
        const saved = { ...this.view };
        try {
            this.fitView();
            this.draw();
            return canvas.toDataURL("image/png").split(",")[1] || null;
        } catch {
            return null;
        } finally {
            this.view.zoom = saved.zoom;
            this.view.x = saved.x;
            this.view.y = saved.y;
            this.draw();
        }
    }

    get scaleMPerPx() {
        return this.props.record.data.scale_m_per_px || DEFAULT_SCALE_M_PER_PX;
    }

    get backgroundUrl() {
        const resId = this.props.record.resId;
        if (!resId || !this.props.record.data.has_background_image) {
            return null;
        }
        return `/web/image/tectora.roof.project/${resId}/background_image`;
    }

    get selectedShape() {
        return this.shapes.find((s) => s.id === this.state.selectedId) || null;
    }

    get scaleLabel() {
        return `${this.scaleMPerPx.toFixed(4)} m/px`;
    }

    // ---------------------------------------------------------------- canvas
    resizeCanvas() {
        const canvas = this.canvasRef();
        const wrapper = this.mainRef() || this.wrapperRef();
        if (!canvas || !wrapper) {
            return;
        }
        const chrome =
            (this.toolbarRef() ? this.toolbarRef().offsetHeight : 0) +
            (this.statusRef() ? this.statusRef().offsetHeight : 0);
        // Fill the space the drawing has: the whole main column in fullscreen,
        // otherwise as much of the window as the form leaves it.
        const width = Math.max(wrapper.clientWidth, 600);
        const height = this.state.fullscreen
            ? Math.max((wrapper.clientHeight || window.innerHeight) - chrome - 2, 320)
            : Math.min(Math.max(window.innerHeight - 300, DEFAULT_CANVAS_HEIGHT), 1400);
        canvas.width = width;
        canvas.height = height;
        // The bitmap is drawn at exactly this size: a CSS width that differs
        // from the pixel width would stretch it and cut the bottom off.
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        // Without a background photo the drawing space is the canvas itself,
        // so the grid fills the screen instead of a letterboxed default.
        if (!this.backgroundImage) {
            this.world = { w: width, h: height };
        }
        this.fitView();
        this.draw();
    }

    toggleFullscreen() {
        this.state.fullscreen = !this.state.fullscreen;
        const wrapper = this.wrapperRef();
        if (wrapper) {
            // Under Odoo's menu bar, which stays usable.
            const navbar = document.querySelector(".o_main_navbar");
            const top = this.state.fullscreen && navbar ? navbar.getBoundingClientRect().bottom : 0;
            wrapper.style.setProperty("--o-roof-mode-top", `${Math.max(top, 0)}px`);
            if (this.state.fullscreen) {
                wrapper.focus({ preventScroll: true }); // keyboard shortcuts work at once
            }
        }
        // The canvas is sized in pixels, so re-measure once the new layout
        // has been painted.
        requestAnimationFrame(() => this.resizeCanvas());
    }

    // "DAK/2026/0023 — Plat dak garages" in the toolbar of the tekenmodus.
    get modeTitle() {
        const data = this.props.record.data;
        return [data.code, data.name].filter((part) => part && typeof part === "string").join(" — ");
    }

    // ------------------------------------------------------------ background
    toggleBackgroundMenu() {
        this.state.bgMenu = !this.state.bgMenu;
    }

    /**
     * Run a server-side change of the background: the record is saved first
     * (the address may have just been typed), then reloaded so the widget
     * sees the new image, scale and bounds, and the drawing is refitted.
     */
    async _withBackgroundChange(label, action) {
        const record = this.props.record;
        if (this.state.bgBusy) {
            return;
        }
        this.state.bgBusy = true;
        this.state.bgMenu = false;
        try {
            if (!(await record.save())) {
                return;
            }
            if (!record.resId) {
                this.notification.add(
                    _t("Sla het dakproject eerst op."), { type: "warning" }
                );
                return;
            }
            await action(record.resId);
            if (this._destroyed) {
                return;
            }
            await record.load();
            // The stored image changed but its URL did not: reload it for real.
            this.backgroundImage = null;
            this.loadBackground(true);
            this.state.showBackground = true;
            if (label) {
                this.state.status = label;
            }
        } catch (error) {
            const message =
                error?.data?.message || error?.message?.message || error?.message || String(error);
            this.notification.add(message, { type: "danger", title: _t("Achtergrond") });
        } finally {
            this.state.bgBusy = false;
        }
    }

    async fetchSatellite() {
        await this._withBackgroundChange(_t("Satellietbeeld opgehaald."), (resId) =>
            this.orm.call("tectora.roof.project", "action_fetch_satellite", [resId])
        );
    }

    chooseUpload() {
        this.bgFileRef()?.click();
    }

    async uploadPlan(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
        await this._withBackgroundChange(
            _t("Plan geladen als achtergrond. Kalibreer de schaal via rechtsklik op een zijdelengte."),
            (resId) =>
                this.orm.write("tectora.roof.project", [resId], { background_image: base64 })
        );
    }

    async clearBackground() {
        await this._withBackgroundChange(_t("Achtergrond verwijderd."), (resId) =>
            this.orm.write("tectora.roof.project", [resId], { background_image: false })
        );
    }

    loadBackground(bustCache = false) {
        let url = this.backgroundUrl;
        if (!url) {
            this.backgroundImage = null;
            const canvas = this.canvasRef();
            this.world = canvas && canvas.width
                ? { w: canvas.width, h: canvas.height }
                : { ...DEFAULT_WORLD };
            this.fitView();
            this.draw();
            return;
        }
        if (bustCache) {
            url += `?t=${Date.now()}`;
        }
        const image = new Image();
        image.onload = () => {
            this.backgroundImage = image;
            this.world = { w: image.naturalWidth, h: image.naturalHeight };
            this.fitView();
            this.draw();
        };
        image.onerror = () => {
            this.backgroundImage = null;
            this.draw();
        };
        image.src = url;
    }

    fitView() {
        const canvas = this.canvasRef();
        if (!canvas) {
            return;
        }
        const zoom = Math.min(
            canvas.width / this.world.w,
            canvas.height / this.world.h
        );
        this.view.zoom = zoom;
        this.view.x = (canvas.width - this.world.w * zoom) / 2;
        this.view.y = (canvas.height - this.world.h * zoom) / 2;
    }

    // Pointer position in canvas pixels (the space view.x/y live in).
    canvasPoint(ev) {
        const canvas = this.canvasRef();
        const rect = canvas.getBoundingClientRect();
        return [
            ((ev.clientX - rect.left) * canvas.width) / rect.width,
            ((ev.clientY - rect.top) * canvas.height) / rect.height,
        ];
    }

    toWorld(ev) {
        const [cx, cy] = this.canvasPoint(ev);
        return [
            (cx - this.view.x) / this.view.zoom,
            (cy - this.view.y) / this.view.zoom,
        ];
    }

    // ------------------------------------------------------------- toolbar
    setTool(tool) {
        this.state.tool = tool;
        this.draftPolygon = null;
        this.draftCursor = null;
        if (tool !== "select") {
            this.state.selectedId = null;
        }
        this.updateStatus();
        this.draw();
    }

    toggleBackground() {
        this.state.showBackground = !this.state.showBackground;
        this.draw();
    }

    toggleGrid() {
        this.state.showGrid = !this.state.showGrid;
        this.draw();
    }

    onOpacityInput(ev) {
        this.state.backgroundOpacity = parseFloat(ev.target.value);
        this.draw();
    }

    // Zoom keeping the given canvas-pixel anchor under the cursor.
    zoomAt(anchorX, anchorY, factor) {
        const newZoom = Math.min(Math.max(this.view.zoom * factor, 0.05), 20);
        if (newZoom === this.view.zoom) {
            return;
        }
        this.view.x = anchorX - ((anchorX - this.view.x) / this.view.zoom) * newZoom;
        this.view.y = anchorY - ((anchorY - this.view.y) / this.view.zoom) * newZoom;
        this.view.zoom = newZoom;
        this.draw();
    }

    zoomBy(factor) {
        const canvas = this.canvasRef();
        this.zoomAt(canvas.width / 2, canvas.height / 2, factor);
    }

    onWheel(ev) {
        if (!ev.deltaY) {
            return;
        }
        // Scroll = zoom on the drawing, centered on the pointer.
        ev.preventDefault();
        const [cx, cy] = this.canvasPoint(ev);
        this.zoomAt(cx, cy, ev.deltaY < 0 ? WHEEL_ZOOM_STEP : 1 / WHEEL_ZOOM_STEP);
    }

    deleteSelected() {
        if (!this.state.selectedId) {
            return;
        }
        this._shapes = this.shapes.filter((s) => s.id !== this.state.selectedId);
        this.state.selectedId = null;
        this.updateStatus();
        this.commit();
    }

    renameSelected() {
        const shape = this.selectedShape;
        if (!shape) {
            return;
        }
        const name = window.prompt("Naam van de sectie:", shape.name || "");
        if (name !== null) {
            shape.name = name.trim();
            this.commit();
        }
    }

    // --------------------------------------------------------------- events
    onPointerDown(ev) {
        if (this.state.contextMenu) {
            this.state.contextMenu = null;
        }
        if (ev.button === 1 || this.state.tool === "pan") {
            this.drag = {
                mode: "pan",
                startX: ev.clientX,
                startY: ev.clientY,
                viewX: this.view.x,
                viewY: this.view.y,
            };
            return;
        }
        if (ev.button !== 0) {
            return;
        }
        const point = this.toWorld(ev);
        // Ctrl (Cmd on a Mac) gathers targets instead of acting on one: no
        // drag, no picker, until Ctrl is released.
        if ((ev.ctrlKey || ev.metaKey) && this.state.tool === "select") {
            ev.preventDefault();
            const hit = this.labelHitTest(point);
            if (hit) {
                this.toggleMultiSelect(hit);
            }
            return;
        }
        if (this.state.tool === "rect") {
            this.drag = { mode: "rect", start: point, current: point };
        } else if (this.state.tool === "polygon" || this.state.tool === "seam") {
            this.addPolygonPoint(point);
        } else if (this.state.tool === "select") {
            const labelHit = this.labelHitTest(point);
            if (labelHit && (labelHit.type === "corner" || labelHit.type === "radius")) {
                // Corner/radius handles: drag reshapes; a plain click on a
                // section corner opens the product picker (see onPointerUp).
                const shape = this.shapes.find((s) => s.id === labelHit.shapeId);
                if (shape) {
                    this.state.selectedId = shape.id;
                    const box = boundingBox(shape.points);
                    this.drag = {
                        mode: labelHit.type === "corner" ? "vertex" : "radius",
                        shape,
                        index: labelHit.edgeIndex,
                        hit: labelHit,
                        startPoint: point,
                        center: [box.x + box.w / 2, box.y + box.h / 2],
                        moved: false,
                        // The seams that end on its sides follow the sides.
                        anchors: this.seamAnchors(shape),
                    };
                    this.updateStatus();
                    this.draw();
                    this.refreshPanel();
                }
                return;
            }
            if (labelHit) {
                // Selects that side, surface or dakobject: the side panel
                // describes it and lists its products (double-click opens
                // the product picker straight away).
                this.focusTarget(labelHit);
                // A dakobject's name label is also where it is grabbed.
                const grabbed = labelHit.type === "surface" &&
                    (labelHit.kind || "section") !== "section" &&
                    this.shapes.find((s) => s.id === labelHit.shapeId);
                if (grabbed) {
                    this.drag = {
                        mode: "move",
                        start: point,
                        original: grabbed.points.map((p) => [...p]),
                        shape: grabbed,
                        moved: false,
                    };
                }
                return;
            }
            const hit = this.hitTest(point);
            const wasSelected = hit && this.state.selectedId === hit.id;
            this.state.selectedId = hit ? hit.id : null;
            this.state.focus = hit ? this.surfaceFocus(hit) : null;
            this.state.copyTargets = [];
            // Moving a roof section requires selecting it first: the first
            // click only selects, dragging an already-selected one moves. A
            // dakobject (chimney, skylight) moves at once: it is small and
            // is placed, not drawn.
            const isObjectHit = hit && !["section", "seam"].includes(hit.kind || "section");
            if (hit && (wasSelected || isObjectHit)) {
                this.drag = {
                    mode: "move",
                    start: point,
                    original: hit.points.map((p) => [...p]),
                    shape: hit,
                    moved: false,
                    // A roof section takes its seams and dakobjecten along.
                    attached: this.attachedShapes(hit).map((shape) => ({
                        shape,
                        original: shape.points.map((p) => [...p]),
                    })),
                };
            }
            this.updateStatus();
            this.draw();
            this.refreshPanel();
        }
    }

    onPointerMove(ev) {
        if (!this.drag && this.draftPolygon) {
            // Live dimensions: the side being drawn follows the pointer.
            this.draftCursor = this.draftSnap(this.toWorld(ev));
            this.draw();
            return;
        }
        if (!this.drag) {
            if (this.state.tool === "select" && this.canvasRef()) {
                const world = this.toWorld(ev);
                const hover = this.labelHitTest(world);
                const isObject = (item) => item && !["section", "seam"].includes(item.kind || "section");
                let cursor = "";
                if (hover) {
                    cursor = hover.type === "corner" || hover.type === "radius" ||
                        (hover.type === "surface" && isObject(hover))
                        ? "move"
                        : "pointer";
                } else if (isObject(this.hitTest(world))) {
                    cursor = "move"; // a dakobject is dragged at once
                }
                this.canvasRef().style.cursor = cursor;
            }
            return;
        }
        if (this.drag.mode === "pan") {
            this.view.x = this.drag.viewX + (ev.clientX - this.drag.startX);
            this.view.y = this.drag.viewY + (ev.clientY - this.drag.startY);
            this.draw();
            return;
        }
        const point = this.toWorld(ev);
        if (this.drag.mode === "rect") {
            this.drag.current = point;
            this.draw();
        } else if (this.drag.mode === "vertex" || this.drag.mode === "radius") {
            if (!this.drag.moved) {
                const [sx, sy] = this.drag.startPoint;
                if (Math.hypot(point[0] - sx, point[1] - sy) < 3 / this.view.zoom) {
                    return;
                }
                this.drag.moved = true;
            }
            if (this.drag.mode === "vertex") {
                this.drag.shape.points[this.drag.index] = [
                    Math.round(point[0] * 100) / 100,
                    Math.round(point[1] * 100) / 100,
                ];
                this.applySeamAnchors(this.drag.shape, this.drag.anchors);
            } else {
                const [cx, cy] = this.drag.center;
                const radius = Math.max(
                    Math.hypot(point[0] - cx, point[1] - cy),
                    2 / this.view.zoom
                );
                this.drag.shape.points = circlePoints(cx, cy, radius);
            }
            this.updateStatus();
            this.draw();
        } else if (this.drag.mode === "move") {
            const dx = point[0] - this.drag.start[0];
            const dy = point[1] - this.drag.start[1];
            if (!this.drag.moved) {
                if (Math.hypot(dx, dy) * this.view.zoom < MOVE_START_SCREEN_PX) {
                    return;
                }
                this.drag.moved = true;
            }
            this.drag.shape.points = this.drag.original.map(([x, y]) => [
                x + dx,
                y + dy,
            ]);
            for (const item of this.drag.attached || []) {
                item.shape.points = item.original.map(([x, y]) => [x + dx, y + dy]);
            }
            this.draw();
        }
    }

    onPointerUp() {
        const drag = this.drag;
        this.drag = null;
        if (!drag) {
            return;
        }
        if (drag.mode === "rect") {
            const [x1, y1] = drag.start;
            const [x2, y2] = drag.current;
            if (
                Math.abs(x2 - x1) >= MIN_RECT_PX &&
                Math.abs(y2 - y1) >= MIN_RECT_PX
            ) {
                const minX = Math.min(x1, x2);
                const maxX = Math.max(x1, x2);
                const minY = Math.min(y1, y2);
                const maxY = Math.max(y1, y2);
                this.addShape([
                    [minX, minY],
                    [maxX, minY],
                    [maxX, maxY],
                    [minX, maxY],
                ]);
            } else {
                this.draw();
            }
        } else if (drag.mode === "move" && drag.moved) {
            this.commit();
        } else if (drag.mode === "vertex" || drag.mode === "radius") {
            if (drag.moved) {
                this.commit();
            } else if (
                drag.mode === "vertex" &&
                (drag.hit.kind || "section") === "section"
            ) {
                // A plain click on a section corner assigns corner products;
                // dakobject corners are drag-only.
                this.openProducts(drag.hit);
            }
        }
    }

    onDblClick(ev) {
        if ((this.state.tool === "polygon" || this.state.tool === "seam") && this.draftPolygon) {
            this.closePolygon();
        } else if (this.state.tool === "select") {
            const point = this.toWorld(ev);
            const labelHit = this.labelHitTest(point);
            if (labelHit && ["surface", "edge", "seam"].includes(labelHit.type)) {
                this.openProducts(labelHit);
                return;
            }
            const hit = this.hitTest(point);
            if (hit) {
                this.state.selectedId = hit.id;
                this.renameSelected();
            }
        }
    }

    onKeyDown(ev) {
        if (ev.target.tagName === "TEXTAREA") {
            return; // typing a description, not drawing
        }
        if (ev.key === "Delete" || ev.key === "Backspace") {
            if (ev.target.tagName !== "INPUT") {
                ev.preventDefault();
                this.deleteSelected();
            }
        } else if (ev.key === "Escape") {
            // Cancel the most local thing first, leave fullscreen last.
            if (this.state.bgMenu) {
                this.state.bgMenu = false;
                return;
            }
            if (this.state.contextMenu) {
                this.state.contextMenu = null;
            } else if (this.state.multiSelect.length) {
                this.clearMultiSelect();
            } else if (this.draftPolygon) {
                this.draftPolygon = null;
                this.draftCursor = null;
            } else if (this.state.fullscreen) {
                this.toggleFullscreen();
            }
            this.updateStatus();
            this.draw();
        } else if (
            (ev.key === "f" || ev.key === "F") &&
            ev.target.tagName !== "INPUT" &&
            !ev.ctrlKey &&
            !ev.metaKey
        ) {
            ev.preventDefault();
            this.toggleFullscreen();
        } else if (ev.key === "Enter" && this.draftPolygon) {
            ev.preventDefault();
            this.closePolygon();
        }
    }

    onContextMenu(ev) {
        ev.preventDefault();
        if (ev.ctrlKey || ev.metaKey) {
            return; // Ctrl-click is the multi-select gesture, not a menu
        }
        const wrapper = this.wrapperRef();
        if (!wrapper) {
            return;
        }
        // Right-clicking a length box edits that side's length; anywhere else
        // opens the "add dakobject" menu.
        const hit = this.labelHitTest(this.toWorld(ev));
        if (hit && hit.type === "edge") {
            this.state.contextMenu = null;
            this.openEdgeLength(hit);
            return;
        }
        const rect = wrapper.getBoundingClientRect();
        this.state.contextMenu = {
            x: ev.clientX - rect.left,
            y: ev.clientY - rect.top,
            worldPoint: this.toWorld(ev),
        };
    }

    addRoofObject(kind, form = "rect") {
        const menu = this.state.contextMenu;
        this.state.contextMenu = null;
        if (!menu) {
            return;
        }
        const sizePx = (OBJECT_DEFAULT_SIZE_M[kind] || 1) / this.scaleMPerPx;
        const [cx, cy] = menu.worldPoint;
        const half = sizePx / 2;
        if (form === "circle") {
            this.addShape(circlePoints(cx, cy, half), kind, "circle");
            return;
        }
        this.addShape(
            [
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half],
            ],
            kind
        );
    }

    // --------------------------------------------------------------- shapes
    /**
     * The point on the outline of a roof section nearest to ``point``,
     * within the snap distance (a corner first): {point, onEdge}. A seam
     * runs from side to side, so its clicks land exactly on the outline.
     */
    seamSnap(point) {
        const snap = CLOSE_SNAP_PX / this.view.zoom;
        let best = null;
        for (const shape of this.shapes) {
            if ((shape.kind || "section") !== "section" || shape.shape === "circle") {
                continue;
            }
            const points = shape.points;
            for (let i = 0; i < points.length; i++) {
                const a = points[i];
                const b = points[(i + 1) % points.length];
                const corner = Math.hypot(point[0] - a[0], point[1] - a[1]);
                if (corner <= snap && (!best || corner - snap < best.distance)) {
                    // A corner wins over a side at the same distance.
                    best = { point: [a[0], a[1]], distance: corner - snap };
                }
                const dx = b[0] - a[0];
                const dy = b[1] - a[1];
                const length2 = dx * dx + dy * dy;
                if (!length2) {
                    continue;
                }
                const t = Math.max(0, Math.min(1,
                    ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2));
                const foot = [a[0] + dx * t, a[1] + dy * t];
                const distance = Math.hypot(point[0] - foot[0], point[1] - foot[1]);
                if (distance <= snap && (!best || distance < best.distance)) {
                    best = { point: foot, distance };
                }
            }
        }
        // An existing seam: a seam can start or end on another one.
        for (const shape of this.shapes) {
            if (!isSeam(shape)) {
                continue;
            }
            const points = shape.points;
            for (let i = 0; i < points.length; i++) {
                const a = points[i];
                const corner = Math.hypot(point[0] - a[0], point[1] - a[1]);
                if (corner <= snap && (!best || corner - snap < best.distance)) {
                    best = { point: [a[0], a[1]], distance: corner - snap };
                }
                const b = points[i + 1];
                if (!b) {
                    continue;
                }
                const dx = b[0] - a[0];
                const dy = b[1] - a[1];
                const length2 = dx * dx + dy * dy;
                if (!length2) {
                    continue;
                }
                const t = Math.max(0, Math.min(1,
                    ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2));
                const foot = [a[0] + dx * t, a[1] + dy * t];
                const distance = Math.hypot(point[0] - foot[0], point[1] - foot[1]);
                if (distance <= snap && (!best || distance < best.distance)) {
                    best = { point: foot, distance };
                }
            }
        }
        return best ? { point: best.point, onEdge: true } : { point, onEdge: false };
    }

    addPolygonPoint(point) {
        if (this.state.tool === "seam") {
            // Click a side, then the other side: the seam is done. Started
            // inside the surface, it takes points until a double-click (or a
            // click on a side).
            const snapped = this.seamSnap(point);
            point = snapped.point;
            if (!this.draftPolygon) {
                this.draftPolygon = [point];
                this.draftCursor = null;
                this.updateStatus();
                this.draw();
                return;
            }
            const last = this.draftPolygon[this.draftPolygon.length - 1];
            if (Math.hypot(point[0] - last[0], point[1] - last[1]) <= CLOSE_SNAP_PX / this.view.zoom) {
                return; // the same spot again (the second click of a double-click)
            }
            this.draftPolygon.push(point);
            if (snapped.onEdge) {
                this.closePolygon();
                this.draw();
                return;
            }
            this.updateStatus();
            this.draw();
            return;
        }
        if (!this.draftPolygon) {
            this.draftPolygon = [point];
            this.draftCursor = null;
        } else {
            const first = this.draftPolygon[0];
            const snap = CLOSE_SNAP_PX / this.view.zoom;
            if (
                this.state.tool !== "seam" &&
                this.draftPolygon.length >= 3 &&
                Math.hypot(point[0] - first[0], point[1] - first[1]) <= snap
            ) {
                this.closePolygon();
                return;
            }
            this.draftPolygon.push(point);
        }
        this.updateStatus();
        this.draw();
    }

    closePolygon() {
        if (this.state.tool === "seam") {
            // An open line: two points make a seam. The roof surface stays
            // one section; the seam divides it into EPDM sheets (the joint
            // between two sheets).
            if (this.draftPolygon && this.draftPolygon.length >= 2) {
                this.addShape(this.draftPolygon, "seam");
                const seam = this._shapes[this._shapes.length - 1];
                this.state.status = _t(
                    "%s getekend: het dakvlak blijft één sectie, de naad deelt het in EPDM-doeken.",
                    seam.name || KIND_NAMES.seam
                );
            }
        } else if (this.draftPolygon && this.draftPolygon.length >= 3) {
            this.addShape(this.draftPolygon);
        }
        this.draftPolygon = null;
        this.draftCursor = null;
        this.updateStatus();
    }

    addShape(points, kind = "section", shapeType = null) {
        const kindCount =
            this.shapes.filter((s) => (s.kind || "section") === kind).length + 1;
        this._shapes = [
            ...this.shapes,
            {
                id: makeId(),
                kind,
                ...(shapeType ? { shape: shapeType } : {}),
                name: `${KIND_NAMES[kind] || KIND_NAMES.section} ${kindCount}`,
                points: points.map(([x, y]) => [
                    Math.round(x * 100) / 100,
                    Math.round(y * 100) / 100,
                ]),
            },
        ];
        this.state.tool = "select";
        this.state.selectedId = this._shapes[this._shapes.length - 1].id;
        this.updateStatus();
        this.commit();
    }

    // A seam marks separate surfaces: every section it crosses is cut in two
    // along it. The halves are new shapes that remember the section they came
    // from, so the server copies its whole-surface products onto both.
    hitTest(point) {
        const shapes = this.shapes;
        const seamTolerance = SEAM_HIT_SCREEN_PX / this.view.zoom;
        // Seams first: a thin line inside a section must stay selectable.
        for (let i = shapes.length - 1; i >= 0; i--) {
            if (isSeam(shapes[i]) && distanceToPolyline(point, shapes[i].points) <= seamTolerance) {
                return shapes[i];
            }
        }
        // Then dakobjecten, which lie on a section: the chimney under the
        // pointer is grabbed, not the roof around it.
        for (let i = shapes.length - 1; i >= 0; i--) {
            const shape = shapes[i];
            if ((shape.kind || "section") !== "section" && !isSeam(shape) &&
                pointInPolygon(point, shape.points)) {
                return shape;
            }
        }
        for (let i = shapes.length - 1; i >= 0; i--) {
            if (!isSeam(shapes[i]) && pointInPolygon(point, shapes[i].points)) {
                return shapes[i];
            }
        }
        return null;
    }

    // ------------------------------------------- selected element (drieluik)
    // A side, a surface or a dakobject can be selected on its own; the side
    // panel then shows three parts for it: the description of its original
    // state, of its future state, and the products assigned to it. The
    // descriptions are kept in the drawing, on the shape:
    // shape.descriptions = {surface: {current, future}, edges: {i: {...}}}.

    surfaceFocus(shape) {
        const kind = shape.kind || "section";
        return {
            type: "surface",
            shapeId: shape.id,
            kind,
            edgeIndex: null,
            hit: {
                type: isSeam(shape) ? "seam" : "surface",
                shapeId: shape.id,
                kind,
                name: shape.name || "",
            },
        };
    }

    focusTarget(hit) {
        this.state.selectedId = hit.shapeId;
        this.state.copyTargets = [];
        this.state.focus = {
            type: hit.type === "edge" ? "edge" : "surface",
            shapeId: hit.shapeId,
            kind: hit.kind || "section",
            edgeIndex: hit.type === "edge" ? hit.edgeIndex : null,
            hit,
        };
        this.updateStatus();
        this.draw();
        this.refreshPanel();
    }

    // The focus, only while its shape is the selected one.
    get focus() {
        const focus = this.state.focus;
        return focus && focus.shapeId === this.state.selectedId && this.selectedShape
            ? focus
            : null;
    }

    get focusLabel() {
        const focus = this.focus;
        if (!focus) {
            return "";
        }
        const shape = this.selectedShape;
        if (focus.type === "edge" && focus.edgeIndex >= 0) {
            const name = shape.name || KIND_NAMES[shape.kind || "section"] || "Naamloos";
            return `${name} — ${this.edgeName(shape, focus.edgeIndex)}`;
        }
        return this.multiSelectLabel({ ...focus.hit, name: shape.name || "" });
    }

    // Where an element keeps its descriptions on its shape; ``focus`` is the
    // element the panel was rendered for (the selection may have moved on by
    // the time a textarea reports its change).
    focusDescriptionEntry(focus = this.focus, create = false) {
        const shape = focus && this.shapes.find((s) => s.id === focus.shapeId);
        if (!shape) {
            return {};
        }
        if (create && !shape.descriptions) {
            shape.descriptions = {};
        }
        const descriptions = shape.descriptions || {};
        if (focus.type === "edge") {
            if (create && !descriptions.edges) {
                descriptions.edges = {};
            }
            const edges = descriptions.edges || {};
            const key = String(focus.edgeIndex);
            if (create && !edges[key]) {
                edges[key] = {};
            }
            return edges[key] || {};
        }
        if (create && !descriptions.surface) {
            descriptions.surface = {};
        }
        return descriptions.surface || {};
    }

    focusDescription(key, focus = this.focus) {
        return this.focusDescriptionEntry(focus)[key] || "";
    }

    setFocusDescription(focus, key, ev) {
        const value = (ev.target.value || "").trim();
        if (!focus || value === this.focusDescription(key, focus)) {
            return;
        }
        const entry = this.focusDescriptionEntry(focus, true);
        if (value) {
            entry[key] = value;
        } else {
            delete entry[key];
        }
        this.commit();
    }

    // The other sides of the focused side's shape, to give them the same
    // description; none for a circle or a naad (no separate sides).
    get focusSideOptions() {
        const focus = this.focus;
        const shape = this.selectedShape;
        if (
            !focus || focus.type !== "edge" || focus.edgeIndex < 0 ||
            !shape || shape.shape === "circle" || isSeam(shape)
        ) {
            return [];
        }
        const points = shape.points;
        const options = [];
        for (let i = 0; i < points.length; i++) {
            if (i === focus.edgeIndex) {
                continue;
            }
            const [ax, ay] = points[i];
            const [bx, by] = points[(i + 1) % points.length];
            const lengthM = Math.hypot(bx - ax, by - ay) * this.scaleMPerPx;
            options.push({
                index: i,
                label: `${this.edgeName(shape, i)} (${lengthM.toFixed(2)} m)`,
                checked: this.state.copyTargets.includes(i),
                described: Boolean(
                    this.focusDescription("current", { ...focus, edgeIndex: i }) ||
                    this.focusDescription("future", { ...focus, edgeIndex: i })
                ),
            });
        }
        return options;
    }

    toggleCopyTarget(index) {
        const targets = this.state.copyTargets;
        this.state.copyTargets = targets.includes(index)
            ? targets.filter((i) => i !== index)
            : [...targets, index];
    }

    selectAllCopyTargets() {
        const options = this.focusSideOptions;
        const all = options.length && options.every((option) => option.checked);
        this.state.copyTargets = all ? [] : options.map((option) => option.index);
    }

    // Give the ticked sides the description (original and future state) of
    // ``focus``; an empty part empties theirs too, so they end up the same.
    applyDescriptionToSides(focus) {
        const targets = [...this.state.copyTargets];
        if (!focus || !targets.length) {
            return;
        }
        const current = this.focusDescription("current", focus);
        const future = this.focusDescription("future", focus);
        for (const index of targets) {
            const entry = this.focusDescriptionEntry({ ...focus, edgeIndex: index }, true);
            for (const [key, value] of [["current", current], ["future", future]]) {
                if (value) {
                    entry[key] = value;
                } else {
                    delete entry[key];
                }
            }
        }
        this.state.copyTargets = [];
        this.commit();
        this.notification.add(
            _t("Beschrijving toegepast op %s zijde(n).", targets.length),
            { type: "success" }
        );
    }

    // The products of the focused element: on a roof section, a side takes
    // its own edge products and those along the whole perimeter, the surface
    // everything else but edges and corners; a dakobject or naad all of its.
    get focusLines() {
        const focus = this.focus;
        const panel = this.state.panel;
        if (!focus || !panel || !panel.lines) {
            return [];
        }
        if (focus.kind !== "section") {
            return panel.lines;
        }
        if (focus.type === "edge") {
            const side = focus.edgeIndex < 0 ? 0 : focus.edgeIndex + 1;
            return panel.lines.filter(
                (line) => line.coverage === "edges" && (!line.edge_index || line.edge_index === side)
            );
        }
        return panel.lines.filter((line) => !["edges", "corners"].includes(line.coverage));
    }

    get focusTotal() {
        return this.focusLines.reduce((sum, line) => sum + (line.price_subtotal || 0), 0);
    }

    addFocusProducts() {
        const focus = this.focus;
        if (focus) {
            this.openProducts({ ...focus.hit, name: this.selectedShape.name || "" });
        }
    }

    // The focused side drawn over the shape, so it is clear which one the
    // panel describes.
    drawFocus(ctx) {
        const focus = this.focus;
        const shape = this.selectedShape;
        if (!focus || focus.type !== "edge" || !shape || focus.edgeIndex < 0) {
            return;
        }
        const points = shape.points;
        const a = points[focus.edgeIndex];
        const b = points[(focus.edgeIndex + 1) % points.length];
        if (!a || !b) {
            return;
        }
        ctx.save();
        ctx.strokeStyle = HIGHLIGHT;
        ctx.lineWidth = 5 / this.view.zoom;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
        ctx.restore();
    }

    // ---------------------------------------------------- attached shapes
    // The seams and dakobjecten drawn on a roof section belong to it: moving
    // the section takes them along, reshaping it keeps the seams' ends on
    // its sides.

    /** Seams lying on ``section`` (all points inside or on its outline) and
     * dakobjecten whose middle is inside it. */
    attachedShapes(section) {
        if ((section.kind || "section") !== "section" || section.shape === "circle") {
            return [];
        }
        const outline = [...section.points, section.points[0]];
        const within = (p) => pointInPolygon(p, section.points) || onPolyline(p, outline);
        return this.shapes.filter((shape) => {
            if (shape === section || !shape.points || !shape.points.length) {
                return false;
            }
            if (isSeam(shape)) {
                return shape.points.every(within);
            }
            if ((shape.kind || "section") === "section") {
                return false;
            }
            const box = boundingBox(shape.points);
            return pointInPolygon([box.x + box.w / 2, box.y + box.h / 2], section.points);
        });
    }

    /** Where the seams of ``section`` touch its sides: per seam point on a
     * side, the side and how far along it. */
    seamAnchors(section) {
        if ((section.kind || "section") !== "section" || section.shape === "circle") {
            return [];
        }
        const points = section.points;
        const anchors = [];
        const seams = this.attachedShapes(section).filter(isSeam);
        for (const seam of seams) {
            seam.points.forEach((p, index) => {
                // On another seam (a T-joint): it follows that seam.
                const host = seams.find((other) => other !== seam && onPolyline(p, other.points));
                if (host && (index === 0 || index === seam.points.length - 1)) {
                    for (let seg = 0; seg < host.points.length - 1; seg++) {
                        const a = host.points[seg];
                        const b = host.points[seg + 1];
                        if (distanceToSegment(p, a, b) <= SEAM_JOIN_PX) {
                            const fromStart = Math.hypot(p[0] - a[0], p[1] - a[1]) <= Math.hypot(p[0] - b[0], p[1] - b[1]);
                            const ref = fromStart ? a : b;
                            const dist = Math.hypot(p[0] - ref[0], p[1] - ref[1]);
                            anchors.push({ seam, index, host, seg, fromStart, dist });
                            return;
                        }
                    }
                }
                for (let edge = 0; edge < points.length; edge++) {
                    const a = points[edge];
                    const b = points[(edge + 1) % points.length];
                    if (distanceToSegment(p, a, b) > SEAM_JOIN_PX) {
                        continue;
                    }
                    // Kept at its distance from the nearer corner of the
                    // side: dragging the far corner leaves it in place.
                    const fromStart = Math.hypot(p[0] - a[0], p[1] - a[1]) <= Math.hypot(p[0] - b[0], p[1] - b[1]);
                    const dist = Math.hypot(p[0] - (fromStart ? a : b)[0], p[1] - (fromStart ? a : b)[1]);
                    anchors.push({ seam, index, edge, fromStart, dist });
                    break;
                }
            });
        }
        return anchors;
    }

    applySeamAnchors(section, anchors) {
        const points = section.points;
        // The ends on the sides first, then those on other seams.
        const ordered = [...(anchors || [])].sort((x, y) => Boolean(x.host) - Boolean(y.host));
        for (const { seam, index, edge, host, seg, fromStart, dist } of ordered) {
            const a = host ? host.points[seg] : points[edge];
            const b = host ? host.points[seg + 1] : points[(edge + 1) % points.length];
            if (!a || !b) {
                continue;
            }
            const [from, to] = fromStart ? [a, b] : [b, a];
            const length = Math.hypot(to[0] - from[0], to[1] - from[1]) || 1;
            const along = Math.min(dist, length);
            const x = from[0] + ((to[0] - from[0]) / length) * along;
            const y = from[1] + ((to[1] - from[1]) / length) * along;
            seam.points[index] = [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
        }
    }

    // ------------------------------------------------------------ EPDM sheets
    // A roof surface stays one section; the seams drawn on it divide it into
    // EPDM sheets, labelled on the drawing.

    get seamLines() {
        return this.shapes.filter((shape) => isSeam(shape)).map((shape) => shape.points);
    }

    sheetPieces(shape) {
        if ((shape.kind || "section") !== "section" || shape.shape === "circle") {
            return [];
        }
        const seams = this.seamLines;
        return seams.length ? splitBySeams(shape.points, seams) : [shape.points];
    }

    drawSheetLabels(ctx) {
        if (!this.seamLines.length) {
            return;
        }
        const zoom = this.view.zoom;
        const scale = this.scaleMPerPx;
        ctx.save();
        ctx.font = `italic ${11 / zoom}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        for (const shape of this.shapes) {
            const pieces = this.sheetPieces(shape);
            if (pieces.length < 2) {
                continue;
            }
            const box = boundingBox(shape.points);
            const labelAt = [box.x + box.w / 2, box.y + box.h / 2];
            pieces.forEach((piece, index) => {
                let [x, y] = polygonCentroid(piece);
                // Clear of the section's own name and area.
                if (Math.hypot(x - labelAt[0], y - labelAt[1]) * zoom < 45) {
                    y += 40 / zoom;
                }
                const area = polygonArea(piece) * scale * scale;
                const text = _t("EPDM-doek %(index)s · %(area)s m²", {
                    index: index + 1,
                    area: area.toFixed(1),
                });
                const width = ctx.measureText(text).width + 10 / zoom;
                ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
                ctx.fillRect(x - width / 2, y - 8 / zoom, width, 16 / zoom);
                ctx.fillStyle = "#475569";
                ctx.fillText(text, x, y);
            });
        }
        ctx.restore();
    }

    /** Sections that were cut by a seam before seams stopped splitting
     * them: the parts touching ``shape`` (and those touching them). */
    splitFamily(shape) {
        if (!shape || (shape.kind || "section") !== "section" || !shape.splitFrom) {
            return [];
        }
        const candidates = this.shapes.filter(
            (s) => (s.kind || "section") === "section" && s.splitFrom && s.shape !== "circle"
        );
        const family = [shape];
        let outline = shape.points;
        let grew = true;
        while (grew) {
            grew = false;
            for (const candidate of candidates) {
                if (family.includes(candidate)) {
                    continue;
                }
                const merged = mergePolygons(outline, candidate.points);
                if (merged) {
                    family.push(candidate);
                    outline = merged;
                    grew = true;
                }
            }
        }
        return family.length > 1 ? family : [];
    }

    get mergeableFamily() {
        return this.splitFamily(this.selectedShape);
    }

    /** One section again from the parts a seam had cut it into: the seams
     * stay, now as the joints between the EPDM sheets. The largest part's
     * section (with its products) carries on. */
    mergeSplitSections() {
        const family = this.mergeableFamily;
        if (!family.length) {
            return;
        }
        const base = [...family].sort((a, b) => polygonArea(b.points) - polygonArea(a.points))[0];
        let outline = base.points;
        const rest = family.filter((s) => s !== base);
        while (rest.length) {
            const index = rest.findIndex((s) => mergePolygons(outline, s.points));
            if (index < 0) {
                break;
            }
            outline = mergePolygons(outline, rest[index].points);
            rest.splice(index, 1);
        }
        // Per-side values follow the side they lay on in one of the parts.
        const sideValue = (key, a, b) => {
            for (const part of family) {
                const values = part[key];
                if (!values) {
                    continue;
                }
                const n = part.points.length;
                for (let i = 0; i < n; i++) {
                    const p = part.points[i];
                    const q = part.points[(i + 1) % n];
                    const on = (pt) => samePoint(pt, p) || samePoint(pt, q) || pointOnSegment(pt, p, q);
                    if (on(a) && on(b) && values[i] !== undefined && values[i] !== "") {
                        return values[i];
                    }
                }
            }
            return undefined;
        };
        const merged = {
            ...base,
            name: (base.name || KIND_NAMES.section).replace(/( [AB])+$/, ""),
            points: outline.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]),
        };
        delete merged.splitFrom;
        for (const key of ["edgeWidths", "edgeUpstands", "edgeNames"]) {
            const values = {};
            merged.points.forEach((a, i) => {
                const value = sideValue(key, a, merged.points[(i + 1) % merged.points.length]);
                if (value !== undefined) {
                    values[i] = value;
                }
            });
            if (Object.keys(values).length) {
                merged[key] = values;
            } else {
                delete merged[key];
            }
        }
        if (merged.descriptions) {
            merged.descriptions = merged.descriptions.surface
                ? { surface: merged.descriptions.surface }
                : undefined;
            if (!merged.descriptions) {
                delete merged.descriptions;
            }
        }
        const removed = new Set(family.filter((s) => s !== base).map((s) => s.id));
        this._shapes = this.shapes
            .filter((s) => !removed.has(s.id))
            .map((s) => (s.id === base.id ? merged : s));
        this.state.selectedId = merged.id;
        this.state.focus = this.surfaceFocus(merged);
        this.commit();
        this.state.status = _t(
            "%(count)s delen samengevoegd tot %(name)s; de naden blijven als grens tussen de EPDM-doeken.",
            { count: family.length, name: merged.name }
        );
        this.refreshPanel();
    }

    // ------------------------------------------------------ quotation build-up
    // Beside the drawing: the quotation as the drawing builds it, per chapter
    // (Afbraak, Opbouw, ...), each line in the colour it has on the drawing.

    scheduleQuote() {
        clearTimeout(this._quoteTimer);
        this._quoteTimer = setTimeout(() => this.loadQuote(), 150);
    }

    async loadQuote() {
        const resId = this.props.record.resId;
        if (!resId || this._destroyed) {
            this.state.quote = null;
            return;
        }
        const ticket = (this._quoteTicket = (this._quoteTicket || 0) + 1);
        this.state.quoteLoading = true;
        try {
            const quote = await this.orm.call(
                "tectora.roof.project", "tectora_get_quote_preview", [[resId]]
            );
            if (ticket !== this._quoteTicket || this._destroyed) {
                return;
            }
            this.state.quote = quote;
        } catch (error) {
            console.warn("Roof canvas: could not load the quotation", error);
        } finally {
            if (ticket === this._quoteTicket) {
                this.state.quoteLoading = false;
            }
        }
        this.draw();
    }

    toggleQuoteOpen() {
        this.state.quoteOpen = !this.state.quoteOpen;
    }

    setQuoteHover(line) {
        const key = line && line.targets.length ? line.key : null;
        if (this.state.quoteHover !== key) {
            this.state.quoteHover = key;
            this.draw();
        }
    }

    /** Whether ``target`` (a part a quotation line comes from) is the
     * element selected on the drawing: the side (its own products, those on
     * every side, the corners at its ends) or the surface (or dakobject). */
    targetOnFocus(target) {
        const focus = this.focus;
        if (!focus || target.canvas_ref !== String(focus.shapeId)) {
            return false;
        }
        if (focus.type === "edge" && focus.edgeIndex >= 0) {
            const side = focus.edgeIndex + 1;
            if (target.coverage === "edges") {
                return !target.edge_index || target.edge_index === side;
            }
            if (target.coverage === "corners") {
                const shape = this.selectedShape;
                const n = shape ? shape.points.length : 0;
                const next = side === n ? 1 : side + 1;
                return !target.edge_index || target.edge_index === side || target.edge_index === next;
            }
            return false;
        }
        if (focus.kind !== "section") {
            return true; // a dakobject: everything on it
        }
        return !["edges", "corners"].includes(target.coverage);
    }

    /** Whether ``line`` is attached to the element selected on the drawing. */
    quoteLineSelected(line) {
        return line.targets.some((target) => this.targetOnFocus(target));
    }

    quoteLineParts(line) {
        if (line.source === "order") {
            return "Op de offerte toegevoegd";
        }
        if (line.project_line) {
            return line.coverage_label ? `${line.coverage_label} · hele dak` : "Hele dak";
        }
        const names = [];
        for (const target of line.targets) {
            const shape = this.shapes.find((s) => String(s.id) === target.canvas_ref);
            const name = (shape && shape.name) || target.name || "";
            let part = name;
            if (target.edge_index) {
                part += target.coverage === "corners"
                    ? ` hoek ${target.edge_index}`
                    : ` zijde ${target.edge_index}`;
            }
            if (part && !names.includes(part)) {
                names.push(part);
            }
        }
        const shown = names.slice(0, 3).join(", ");
        const more = names.length > 3 ? ` +${names.length - 3}` : "";
        return `${line.coverage_label} · ${shown}${more}`;
    }

    formatQuantity(value) {
        return (Math.round((value || 0) * 100) / 100).toLocaleString("nl-BE");
    }

    /** A click on a quotation line selects the part of the drawing it comes from. */
    selectQuoteLine(line) {
        const target = line.targets[0];
        const shape = target && this.shapes.find((s) => String(s.id) === target.canvas_ref);
        if (!shape) {
            return;
        }
        if (target.coverage === "edges" && target.edge_index && !isSeam(shape)
                && shape.shape !== "circle") {
            this.focusTarget({
                type: "edge",
                shapeId: shape.id,
                kind: shape.kind || "section",
                edgeIndex: target.edge_index - 1,
                name: shape.name || "",
            });
            return;
        }
        this.state.selectedId = shape.id;
        this.state.focus = this.surfaceFocus(shape);
        this.state.copyTargets = [];
        this.updateStatus();
        this.draw();
        this.refreshPanel();
    }

    async openQuoteOrder() {
        const quote = this.state.quote;
        if (!quote || !quote.order_id) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: quote.order_id,
            views: [[false, "form"]],
        });
    }

    /** The outline of a shape as segments, for the colour marks. */
    quoteOutline(shape) {
        let points = shape.points || [];
        if (shape.shape === "circle") {
            const box = boundingBox(points);
            points = circlePoints(box.x + box.w / 2, box.y + box.h / 2, Math.max(box.w, box.h) / 2);
        }
        const closed = !isSeam(shape);
        const segments = [];
        const n = points.length;
        for (let i = 0; i < (closed ? n : n - 1); i++) {
            segments.push([points[i], points[(i + 1) % n]]);
        }
        return { points, segments, closed };
    }

    /**
     * The parts of the drawing the hovered quotation line comes from, in the
     * highlight colour: its sides, corners and surfaces. Nothing is drawn
     * while no line is hovered; the selected side is drawFocus's.
     */
    drawQuoteMarks(ctx) {
        const quote = this.state.quote;
        const hover = this.state.quoteHover;
        if (!quote || !hover) {
            return;
        }
        const line = quote.chapters.flatMap((chapter) => chapter.lines).find((l) => l.key === hover);
        if (!line) {
            return;
        }
        const zoom = this.view.zoom;
        ctx.save();
        ctx.strokeStyle = HIGHLIGHT;
        ctx.fillStyle = HIGHLIGHT;
        ctx.lineCap = "round";
        for (const target of line.targets) {
            const shape = this.shapes.find((s) => String(s.id) === target.canvas_ref);
            if (!shape || !shape.points || !shape.points.length) {
                continue;
            }
            const { points, segments } = this.quoteOutline(shape);
            if (target.coverage === "edges") {
                ctx.globalAlpha = 1;
                ctx.lineWidth = 6 / zoom;
                segments.forEach(([a, b], i) => {
                    if (target.edge_index && shape.shape !== "circle" && target.edge_index !== i + 1) {
                        return;
                    }
                    ctx.beginPath();
                    ctx.moveTo(a[0], a[1]);
                    ctx.lineTo(b[0], b[1]);
                    ctx.stroke();
                });
            } else if (target.coverage === "corners") {
                ctx.globalAlpha = 1;
                points.forEach(([x, y], i) => {
                    if (target.edge_index && target.edge_index !== i + 1) {
                        return;
                    }
                    ctx.beginPath();
                    ctx.arc(x, y, 7 / zoom, 0, Math.PI * 2);
                    ctx.fill();
                });
            } else if (!isSeam(shape)) {
                ctx.globalAlpha = 0.25;
                ctx.beginPath();
                ctx.moveTo(points[0][0], points[0][1]);
                for (let i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i][0], points[i][1]);
                }
                ctx.closePath();
                ctx.fill();
                ctx.globalAlpha = 1;
                ctx.lineWidth = 3 / zoom;
                ctx.stroke();
            } else {
                ctx.globalAlpha = 1;
                ctx.lineWidth = 6 / zoom;
                ctx.beginPath();
                ctx.moveTo(points[0][0], points[0][1]);
                for (let i = 1; i < points.length; i++) {
                    ctx.lineTo(points[i][0], points[i][1]);
                }
                ctx.stroke();
            }
        }
        ctx.restore();
    }

    // ------------------------------------------------------- product panel
    coverageLabel(line) {
        const labels = {
            surface: "Oppervlak",
            edges: "Randen",
            corners: "Hoeken",
            drainage: "Afvoer",
            general: "Algemeen",
        };
        const label = labels[line.coverage] || line.coverage;
        return line.side_display ? `${label} · ${line.side_display}` : label;
    }

    closePanel() {
        this.state.selectedId = null;
        this.state.focus = null;
        this.state.panel = null;
        this.updateStatus();
        this.draw();
    }

    async refreshPanel() {
        // Whatever changed the panel (products, measurements) changes the
        // quotation too.
        this.scheduleQuote();
        try {
            await this._refreshPanel();
        } catch (error) {
            console.warn("Roof canvas: could not refresh product panel", error);
        }
    }

    panelGeometry(shape) {
        if (shape.shape === "circle" || isSeam(shape)) {
            return { edges: [], inner: null };
        }
        const scale = this.scaleMPerPx;
        const n = shape.points.length;
        const edges = shape.points.map((point, index) => {
            const next = shape.points[(index + 1) % n];
            return {
                index,
                label: this.edgeName(shape, index),
                customName: (shape.edgeNames && shape.edgeNames[index]) || "",
                lengthM:
                    Math.hypot(next[0] - point[0], next[1] - point[1]) * scale,
                width: this.edgeWidth(shape, index),
                upstand: this.edgeUpstand(shape, index),
            };
        });
        const innerPoints = this.innerPolygon(shape);
        const inner = innerPoints
            ? {
                  area: polygonArea(innerPoints) * scale * scale,
                  perimeter: polygonPerimeter(innerPoints) * scale,
              }
            : null;
        // Vertical surface of the upstands: per side length x height.
        const upstandArea = edges.reduce(
            (sum, edge) => sum + edge.lengthM * edge.upstand, 0
        );
        const upstandLength = edges.reduce(
            (sum, edge) => sum + (edge.upstand ? edge.lengthM : 0), 0
        );
        return {
            edges,
            inner,
            upstand: upstandArea
                ? { area: upstandArea, length: upstandLength }
                : null,
        };
    }

    setEdgeWidth(edge, ev) {
        this.setEdgeValue("edgeWidths", edge, ev);
    }

    setEdgeUpstand(edge, ev) {
        this.setEdgeValue("edgeUpstands", edge, ev);
    }

    // Copy one side's rand and opstand to every side of the shape. Only the
    // values that are filled in are copied: a side with no width must not
    // wipe the widths of the others, which is what makes this safe to click.
    applyEdgeValuesToAll(edge) {
        const shape = this.selectedShape;
        if (!shape || !shape.points) {
            return;
        }
        const width = this.edgeWidth(shape, edge.index);
        const upstand = this.edgeUpstand(shape, edge.index);
        if (!width && !upstand) {
            return;
        }
        const count = shape.points.length;
        for (const [key, value] of [
            ["edgeWidths", width],
            ["edgeUpstands", upstand],
        ]) {
            if (!value) {
                continue;
            }
            const values = { ...(shape[key] || {}) };
            for (let i = 0; i < count; i++) {
                values[i] = value;
            }
            shape[key] = values;
        }
        this.updateStatus();
        this.commit();
        this.refreshPanel();
        const parts = [];
        if (width) {
            parts.push(_t("breedte %s cm", Math.round(width * 1000) / 10));
        }
        if (upstand) {
            parts.push(_t("opstand %s cm", Math.round(upstand * 1000) / 10));
        }
        this.notification.add(
            _t("%(values)s toegepast op alle %(count)s zijden.",
               { values: parts.join(" en "), count }),
            { type: "success" }
        );
    }

    applyEverywhereTitle(edge) {
        const shape = this.selectedShape;
        const count = shape && shape.points ? shape.points.length : 0;
        if (!edge.width && !edge.upstand) {
            return _t("Vul eerst een breedte of opstand in op deze zijde.");
        }
        const parts = [];
        if (edge.width) {
            parts.push(_t("breedte %s cm", Math.round(edge.width * 1000) / 10));
        }
        if (edge.upstand) {
            parts.push(_t("opstand %s cm", Math.round(edge.upstand * 1000) / 10));
        }
        return _t(
            "Overal toepassen: %(values)s op alle %(count)s zijden. Wat hier " +
                "leeg staat, blijft op de andere zijden ongewijzigd.",
            { values: parts.join(" en "), count }
        );
    }

    setEdgeName(edge, ev) {
        const shape = this.selectedShape;
        if (!shape) {
            return;
        }
        const value = (ev.target.value || "").trim();
        const names = { ...(shape.edgeNames || {}) };
        if (value) {
            names[edge.index] = value;
        } else {
            delete names[edge.index];
        }
        if (Object.keys(names).length) {
            shape.edgeNames = names;
        } else {
            delete shape.edgeNames;
        }
        this.commit();
        this.refreshPanel();
    }

    // The measurements of a selected dakobject, for the side panel.
    get focusObjectMeasures() {
        const focus = this.focus;
        const shape = this.selectedShape;
        if (!focus || focus.kind === "section" || !shape || isSeam(shape)) {
            return null;
        }
        const m = this.measurements(shape.points);
        const object = this.state.panel && this.state.panel.object;
        const height = object ? object.height : 0;
        return {
            kind: shape.kind,
            isCircle: shape.shape === "circle",
            size: shape.shape === "circle"
                ? `Ø ${m.width.toFixed(2)} m`
                : `${m.width.toFixed(2)} × ${m.length.toFixed(2)} m`,
            width: m.width,
            length: m.length,
            area: m.area,
            perimeter: m.perimeter,
            editableHeight: Boolean(object),
            height,
            sideArea: m.perimeter * height,
            volume: m.area * height,
        };
    }

    // Lengte / breedte of a dakobject typed in the panel: the shape is
    // stretched around its centre (a circle keeps its shape: the diameter).
    setObjectSize(dimension, ev) {
        const shape = this.selectedShape;
        const meters = parseFloat(ev.target.value);
        if (!shape || !(meters > 0)) {
            return;
        }
        const target = meters / this.scaleMPerPx;
        const box = boundingBox(shape.points);
        const cx = box.x + box.w / 2;
        const cy = box.y + box.h / 2;
        if (shape.shape === "circle") {
            shape.points = circlePoints(cx, cy, target / 2);
        } else if (dimension === "width" && box.w > 0) {
            const factor = target / box.w;
            shape.points = shape.points.map(([x, y]) => [cx + (x - cx) * factor, y]);
        } else if (dimension === "length" && box.h > 0) {
            const factor = target / box.h;
            shape.points = shape.points.map(([x, y]) => [x, cy + (y - cy) * factor]);
        } else {
            return;
        }
        shape.points = shape.points.map(([x, y]) => [
            Math.round(x * 100) / 100, Math.round(y * 100) / 100,
        ]);
        this.updateStatus();
        this.commit();
        this.refreshPanel();
    }

    // Hoogte of a dakobject, written on its record.
    async setObjectHeight(ev) {
        const object = this.state.panel && this.state.panel.object;
        const value = parseFloat(ev.target.value);
        if (!object || !(value >= 0)) {
            return;
        }
        try {
            await this.orm.write("tectora.roof.object", [object.id], {
                height: Math.round(value * 100) / 100,
            });
        } catch (error) {
            console.warn("Roof canvas: could not save the height", error);
            return;
        }
        await this.refreshPanel();
    }

    // The focused side's row of the panel geometry (width, upstand, length).
    get focusEdge() {
        const focus = this.focus;
        const panel = this.state.panel;
        if (!focus || focus.type !== "edge" || !panel || !panel.edges) {
            return null;
        }
        return panel.edges.find((edge) => edge.index === focus.edgeIndex) || null;
    }

    setEdgeValue(key, edge, ev) {
        const shape = this.selectedShape;
        if (!shape) {
            return;
        }
        // Typed in cm, kept in m.
        const value = parseFloat(String(ev.target.value).replace(",", ".")) / 100;
        const values = { ...(shape[key] || {}) };
        if (value > 0) {
            values[edge.index] = Math.round(value * 1000) / 1000;
        } else {
            delete values[edge.index];
        }
        if (Object.keys(values).length) {
            shape[key] = values;
        } else {
            delete shape[key];
        }
        this.commit();
        this.refreshPanel();
    }

    // ------------------------------------------------- side length / calibration
    edgeLengthM(shape, edgeIndex) {
        const n = shape.points.length;
        const [x1, y1] = shape.points[edgeIndex];
        const [x2, y2] = shape.points[(edgeIndex + 1) % n];
        return Math.hypot(x2 - x1, y2 - y1) * this.scaleMPerPx;
    }

    // Real length of the clicked side, entered by the user. Opened by
    // right-clicking a length box.
    openEdgeLength(hit) {
        const shape = this.shapes.find((s) => s.id === hit.shapeId);
        if (!shape || !shape.points || shape.points.length < 3) {
            return;
        }
        const isCircle = shape.shape === "circle";
        const index = isCircle ? -1 : hit.edgeIndex;
        const current = isCircle
            ? polygonPerimeter(shape.points) * this.scaleMPerPx
            : this.edgeLengthM(shape, index);
        if (!(current > 0)) {
            return;
        }
        const name = shape.name || KIND_NAMES[shape.kind || "section"] || "Vorm";
        const n = shape.points.length;
        this.state.selectedId = shape.id;
        this.updateStatus();
        this.draw();
        this.refreshPanel();
        this.dialog.add(RoofEdgeLengthDialog, {
            title: isCircle
                ? `${name} — omtrek aanpassen`
                : `${name} — zijde ${index + 1} aanpassen`,
            currentLength: current,
            currentScale: this.scaleMPerPx,
            lengthLabel: isCircle ? "Omtrek" : "Lengte",
            allowAnchor: !isCircle,
            startPoint: index + 1,
            endPoint: ((index + 1) % n) + 1,
            onConfirm: (result) => this.applyEdgeLength(shape, index, result),
        });
    }

    applyEdgeLength(shape, index, { length, scaleAll, anchor }) {
        const isCircle = shape.shape === "circle";
        const current = isCircle
            ? polygonPerimeter(shape.points) * this.scaleMPerPx
            : this.edgeLengthM(shape, index);
        if (!(current > 0) || !(length > 0)) {
            return;
        }
        const factor = length / current;
        if (Math.abs(factor - 1) < 1e-9) {
            return;
        }
        if (scaleAll) {
            this.recalibrateScale(this.scaleMPerPx * factor);
            return;
        }
        if (isCircle) {
            // Keep it a circle: same center, radius scaled to the new
            // circumference.
            const box = boundingBox(shape.points);
            const radius = (Math.max(box.w, box.h) / 2) * factor;
            shape.points = circlePoints(
                box.x + box.w / 2, box.y + box.h / 2, Math.max(radius, 1e-3)
            );
        } else {
            const anchors = this.seamAnchors(shape);
            shape.points = resizeEdgePoints(
                shape.points, index, length / this.scaleMPerPx, anchor
            );
            this.applySeamAnchors(shape, anchors);
        }
        this.updateStatus();
        this.commit();
        this.refreshPanel();
    }

    // Calibrate the map scale from one measured side. Nothing moves in world
    // (= background image pixel) coordinates, so the drawing stays exactly on
    // the satellite image; the grid derives its spacing from the scale and
    // therefore re-steps itself to real meters, and every other length and
    // surface in the project scales along.
    async recalibrateScale(newScale) {
        const scale = Math.min(Math.max(newScale, 1e-6), 100);
        try {
            await this.props.record.update({ scale_m_per_px: scale });
        } catch (error) {
            console.warn("Roof canvas: could not update the scale", error);
            this.notification.add(
                _t("De schaal kon niet worden aangepast."), { type: "danger" }
            );
            return;
        }
        if (this._destroyed) {
            return;
        }
        this.updateStatus();
        this.commit();
        this.refreshPanel();
        this.notification.add(
            _t(
                "Schaal gekalibreerd op %s m/px — alle maten en het meetraster " +
                "zijn proportioneel aangepast.",
                scale.toFixed(4)
            ),
            { type: "success" }
        );
    }

    async _refreshPanel() {
        const shape = this.selectedShape;
        const record = this.props.record;
        if (!shape || !record.resId) {
            this.state.panel = null;
            return;
        }
        const isObject = (shape.kind || "section") !== "section";
        const targetModel = isObject
            ? "tectora.roof.object"
            : "tectora.roof.section";
        this.state.panel = {
            name: shape.name || "Naamloos",
            lines: [],
            total: 0,
            loading: true,
            synced: true,
            ...this.panelGeometry(shape),
        };
        const targetIds = await this.orm.search(
            targetModel,
            [
                ["project_id", "=", record.resId],
                ["canvas_ref", "=", shape.id],
            ],
            { limit: 1 }
        );
        if (this.selectedShape !== shape || !this.state.panel) {
            return; // selection changed while loading
        }
        if (!targetIds.length) {
            this.state.panel.loading = false;
            this.state.panel.synced = false;
            return;
        }
        const lines = await this.orm.searchRead(
            "tectora.roof.section.product",
            [[isObject ? "object_id" : "section_id", "=", targetIds[0]]],
            ["product_id", "coverage", "side_display", "edge_index", "quantity", "uom_id", "price_subtotal"]
        );
        // A dakobject's height lives on its record (the drawing is 2D).
        let object = null;
        if (isObject) {
            const [row] = await this.orm.read("tectora.roof.object", [targetIds[0]], ["height"]);
            object = { id: targetIds[0], height: (row && row.height) || 0 };
        }
        if (this.selectedShape !== shape) {
            return;
        }
        this.state.panel = {
            name: shape.name || "Naamloos",
            lines,
            object,
            total: lines.reduce((sum, line) => sum + (line.price_subtotal || 0), 0),
            loading: false,
            synced: true,
            ...this.panelGeometry(shape),
        };
    }

    async removeLine(line) {
        try {
            await this.orm.unlink("tectora.roof.section.product", [line.id]);
            await this.props.record.load();
        } catch (error) {
            console.warn("Roof canvas: could not remove product line", error);
        }
        this.refreshPanel();
    }

    // ------------------------------------------------- multiple sides at once
    // Ctrl-click gathers sides (or surfaces, or corners); releasing Ctrl opens
    // the picker once for all of them.
    hitTargetKey(hit) {
        const side =
            hit.type === "surface" || hit.type === "seam" ? 0 : (hit.edgeIndex || 0) + 1;
        return `${hit.shapeId}|${hit.type}|${side}`;
    }

    // Two hits can share a selection only if the same product categories apply
    // to both: type, section-or-dakobject, and for corners inner-or-outer.
    sameFamily(a, b) {
        return (
            a.type === b.type &&
            (a.kind || "section") === (b.kind || "section") &&
            (a.type !== "corner" || a.cornerType === b.cornerType)
        );
    }

    toggleMultiSelect(hit) {
        if (!["edge", "surface", "corner", "seam"].includes(hit.type)) {
            return;
        }
        if (hit.type === "corner" && (hit.kind || "section") !== "section") {
            return; // corner products only apply to roof sections
        }
        const key = this.hitTargetKey(hit);
        const current = this.state.multiSelect;
        const existing = current.findIndex((item) => this.hitTargetKey(item) === key);
        if (existing >= 0) {
            this.state.multiSelect = current.filter((_, i) => i !== existing);
        } else if (current.length && !this.sameFamily(current[0], hit)) {
            // A different kind of target starts a new selection: mixing them
            // would mean mixing product categories.
            this.state.multiSelect = [hit];
        } else {
            this.state.multiSelect = [...current, hit];
        }
        this.state.selectedId = hit.shapeId;
        this.updateStatus();
        this.draw();
    }

    // "Sectie 1 — zijde 2", the way the picker and the status bar name a target.
    multiSelectLabel(hit) {
        const name = hit.name || KIND_NAMES[hit.kind || "section"] || "Naamloos";
        if (hit.type === "surface") {
            return name;
        }
        if (hit.type === "seam") {
            return `${name} — naad`;
        }
        if (hit.type === "corner") {
            const kind = hit.cornerType === "inner" ? "binnenhoek" : "buitenhoek";
            return `${name} — ${kind} ${hit.edgeIndex + 1}`;
        }
        if (hit.edgeIndex < 0) {
            return `${name} — omtrek`;
        }
        return `${name} — zijde ${hit.edgeIndex + 1}`;
    }

    isMultiSelected(hit) {
        const key = this.hitTargetKey(hit);
        return this.state.multiSelect.some(
            (item) => this.hitTargetKey(item) === key
        );
    }

    clearMultiSelect() {
        if (this.state.multiSelect.length) {
            this.state.multiSelect = [];
            this.updateStatus();
            this.draw();
        }
    }

    flushMultiSelect() {
        const hits = this.state.multiSelect;
        if (!hits.length || this._destroyed) {
            return;
        }
        this.state.multiSelect = [];
        this.updateStatus();
        this.draw();
        const [base, ...extra] = hits;
        this.openProducts(base, extra);
    }

    labelHitTest([px, py]) {
        for (let i = this.labelHits.length - 1; i >= 0; i--) {
            const hit = this.labelHits[i];
            if (
                px >= hit.x && px <= hit.x + hit.w &&
                py >= hit.y && py <= hit.y + hit.h
            ) {
                return hit;
            }
        }
        return null;
    }

    // Every item in the drawing of the same type as the clicked one, so the
    // same products can be assigned to several at once. Built from the shapes
    // rather than from the drawn labels: a side too short for a length box
    // must still be selectable.
    sameTypeTargets(hit) {
        const type = hit.type;
        if (!["surface", "edge", "corner", "seam"].includes(type)) {
            return [];
        }
        const isObject = (hit.kind || "section") !== "section";
        const wantsInner = hit.cornerType === "inner";
        const targets = [];
        for (const shape of this.shapes) {
            if (isSeam(shape) !== (type === "seam")) {
                continue; // seams take their own products
            }
            if (type === "seam") {
                const length = polygonPerimeter(shape.points || [], false) * this.scaleMPerPx;
                targets.push({
                    shapeId: shape.id,
                    kind: "seam",
                    key: `${shape.id}|seam|0`,
                    sideNumber: 0,
                    quantity: Math.round(length * 100) / 100,
                    label: shape.name || KIND_NAMES.seam,
                    detail: `${length.toFixed(2)} m`,
                });
                continue;
            }
            if (((shape.kind || "section") !== "section") !== isObject) {
                continue; // dakobjecten and daksecties take different products
            }
            const points = shape.points || [];
            if (points.length < 3) {
                continue;
            }
            const isCircle = shape.shape === "circle";
            const name =
                shape.name || KIND_NAMES[shape.kind || "section"] || "Naamloos";
            const base = { shapeId: shape.id, kind: shape.kind || "section" };
            if (type === "surface") {
                const area = polygonArea(points) * this.scaleMPerPx ** 2;
                targets.push({
                    ...base,
                    key: `${shape.id}|surface|0`,
                    sideNumber: 0,
                    quantity: Math.round(area * 100) / 100,
                    label: name,
                    detail: `${area.toFixed(2)} m²`,
                });
            } else if (type === "edge" && isCircle) {
                const length = polygonPerimeter(points) * this.scaleMPerPx;
                targets.push({
                    ...base,
                    key: `${shape.id}|edge|0`,
                    sideNumber: 0,
                    quantity: Math.round(length * 100) / 100,
                    label: `${name} — omtrek`,
                    detail: `${length.toFixed(2)} m`,
                });
            } else if (type === "edge") {
                for (let i = 0; i < points.length; i++) {
                    const length = this.edgeLengthM(shape, i);
                    targets.push({
                        ...base,
                        key: `${shape.id}|edge|${i + 1}`,
                        sideNumber: i + 1,
                        quantity: Math.round(length * 100) / 100,
                        label: `${name} — zijde ${i + 1}`,
                        detail: `${length.toFixed(2)} m`,
                    });
                }
            } else if (type === "corner" && !isCircle) {
                for (let i = 0; i < points.length; i++) {
                    // Inner and outer corners take different product
                    // categories, so only offer corners of the same sort.
                    if (isInnerCorner(points, i) !== wantsInner) {
                        continue;
                    }
                    targets.push({
                        ...base,
                        key: `${shape.id}|corner|${i + 1}`,
                        sideNumber: i + 1,
                        quantity: 1,
                        label: `${name} — ${
                            wantsInner ? "binnenhoek" : "buitenhoek"
                        } ${i + 1}`,
                        detail: "1",
                    });
                }
            }
        }
        return targets;
    }

    // ---------------------------------------------------- products via labels
    // `extraHits` are the other Ctrl-selected targets: they arrive pre-ticked
    // in the picker's "meerdere items" list, so one confirmation covers them
    // all.
    async openProducts(hit, extraHits = []) {
        if (hit.type === "corner" && (hit.kind || "section") !== "section") {
            return; // corner products only apply to roof sections
        }
        const record = this.props.record;
        const isObject = (hit.kind || "section") !== "section";
        const targetModel = isObject
            ? "tectora.roof.object"
            : "tectora.roof.section";
        let targetIds;
        let recordByShape = {}; // canvas_ref -> section/object id
        const loadRecords = async () => {
            const records = await this.orm.searchRead(
                targetModel, [["project_id", "=", record.resId]], ["canvas_ref"]
            );
            recordByShape = Object.fromEntries(
                records
                    .filter((row) => row.canvas_ref)
                    .map((row) => [row.canvas_ref, row.id])
            );
            return recordByShape[hit.shapeId] ? [recordByShape[hit.shapeId]] : [];
        };
        try {
            // The section/object records are created server-side from the
            // drawing, so the project must be saved (synced) before lines
            // can attach.
            if (!(await record.save())) {
                this.notification.add(
                    _t(
                        "Producten koppelen kan pas nadat het project is " +
                        "opgeslagen. Vul de verplichte velden in (zoals de " +
                        "projectnaam) en klik daarna opnieuw op het label."
                    ),
                    { type: "warning" }
                );
                return;
            }
            targetIds = await loadRecords();
            if (!targetIds.length) {
                // The shape was drawn but never synced: run the sync for the
                // user (same as 'Meting bijwerken uit tekening') and retry.
                await this.orm.call(
                    "tectora.roof.project", "action_sync_from_canvas",
                    [record.resId], { context: { tectora_quiet_sync: true } }
                );
                await record.load();
                this.draw();
                targetIds = await loadRecords();
            }
        } catch (error) {
            console.warn("Roof canvas: preparing product assignment failed", error);
            return;
        }
        if (!targetIds.length) {
            this.notification.add(
                _t(
                    "Er bestaat nog geen sectie of dakobject voor deze vorm. " +
                    "Klik eerst op 'Meting bijwerken uit tekening'."
                ),
                { type: "warning" }
            );
            return;
        }
        const isSurface = hit.type === "surface";
        const isCorner = hit.type === "corner";
        const isSeamHit = hit.type === "seam";
        const sideNumber = isSurface || isSeamHit ? 0 : hit.edgeIndex + 1;
        const quantity = isCorner
            ? 1
            : Math.round((isSurface ? hit.areaM2 : hit.lengthM) * 100) / 100;
        const shapeName = hit.name || _t("Naamloos");
        let target;
        if (isSeamHit) {
            target = _t("%(shape)s — naad (%(qty)s m)", {
                shape: shapeName,
                qty: quantity.toFixed(2),
            });
        } else if (isSurface) {
            target = _t("%(shape)s — oppervlak (%(qty)s m²)", {
                shape: shapeName,
                qty: quantity.toFixed(2),
            });
        } else if (isCorner) {
            target = _t("%(shape)s — %(kind)s %(side)s", {
                shape: shapeName,
                kind: hit.cornerType === "inner" ? _t("binnenhoek") : _t("buitenhoek"),
                side: sideNumber,
            });
        } else if (sideNumber) {
            target = _t("%(shape)s — zijde %(side)s (%(qty)s m)", {
                shape: shapeName,
                side: sideNumber,
                qty: quantity.toFixed(2),
            });
        } else {
            // Circles: one undivided outline instead of numbered sides.
            target = _t("%(shape)s — omtrek (%(qty)s m)", {
                shape: shapeName,
                qty: quantity.toFixed(2),
            });
        }
        // Strict whitelist: a category only shows up for the targets listed
        // in its 'Kan gebruikt worden voor'; categories without any usage
        // never appear in the canvas assignment dialog.
        let usages;
        if (isSeamHit) {
            usages = ["seam"];
        } else if (isObject) {
            usages = ["object"];
        } else if (isCorner) {
            usages = [
                "corner",
                hit.cornerType === "inner" ? "corner_inner" : "corner_outer",
            ];
        } else if (isSurface) {
            usages = ["surface"];
        } else {
            usages = ["edge"];
        }
        const coverage = isCorner ? "corners" : isSurface ? "surface" : "edges";
        const linkField = isObject ? "object_id" : "section_id";
        const clickedKey = `${hit.shapeId}|${hit.type}|${sideNumber}`;
        // The other items of the same type, minus the one that was clicked and
        // any shape the server does not have a record for yet.
        const others = this.sameTypeTargets(hit).filter(
            (item) => item.key !== clickedKey && recordByShape[item.shapeId]
        );
        const available = new Set(others.map((item) => item.key));
        const preselected = extraHits
            .map((extra) => this.hitTargetKey(extra))
            .filter((key) => key !== clickedKey && available.has(key));
        // The categories offered here: their own usages, or (a new
        // sub-category such as Isolatie/PIR) those of their parent.
        let categoryIds = [];
        try {
            categoryIds = await this.orm.call(
                "product.category", "tectora_category_ids_for_usages", [usages]
            );
        } catch (error) {
            console.warn("Roof canvas: could not load the product categories", error);
        }
        // The sections a choice in the dialog goes to: the clicked surface
        // and the other surfaces ticked.
        const sectionIdsFor = (targetKeys) => {
            const picked = new Set(targetKeys || []);
            return [
                targetIds[0],
                ...others
                    .filter((item) => picked.has(item.key))
                    .map((item) => recordByShape[item.shapeId]),
            ].filter(Boolean);
        };
        const buildup = isSurface && !isObject
            ? {
                  projectId: record.resId,
                  previewVapour: (targetKeys, insulationId) =>
                      this.orm.call(
                          "tectora.roof.project", "tectora_preview_vapour",
                          [[record.resId], sectionIdsFor(targetKeys)],
                          { insulation_id: insulationId || false }
                      ),
                  preview: (targetKeys, amounts) =>
                      this.orm.call(
                          "tectora.roof.project", "tectora_preview_epdm_sheets",
                          [[record.resId], sectionIdsFor(targetKeys)],
                          { margin: amounts.margin, seam_overlap: amounts.seam_overlap }
                      ),
                  apply: (choice, targetKeys) => this.applyBuildup(sectionIdsFor(targetKeys), choice),
              }
            : undefined;
        // A side of a roof surface: the Randafwerking (roof edge or
        // connection) for it and the other sides ticked.
        const edgeItemsFor = (targetKeys) => {
            const picked = new Set(targetKeys || []);
            return [
                { section_id: targetIds[0], shape_id: hit.shapeId, side: sideNumber, quantity },
                ...others
                    .filter((item) => picked.has(item.key) && item.sideNumber)
                    .map((item) => ({
                        section_id: recordByShape[item.shapeId],
                        shape_id: item.shapeId,
                        side: item.sideNumber,
                        quantity: item.quantity,
                    })),
            ].filter((item) => item.section_id && item.side);
        };
        const clickedShape = this.shapes.find((shape) => shape.id === hit.shapeId);
        const edges = hit.type === "edge" && !isObject && sideNumber
            ? {
                  projectId: record.resId,
                  // The side's roof edge as drawn: width and upstand (m).
                  width: clickedShape ? this.edgeWidth(clickedShape, sideNumber - 1) : 0,
                  upstand: clickedShape ? this.edgeUpstand(clickedShape, sideNumber - 1) : 0,
                  apply: (choice, targetKeys, dryRun) =>
                      dryRun
                          ? this.orm.call(
                                "tectora.roof.project", "tectora_apply_edges",
                                [[record.resId], edgeItemsFor(targetKeys), choice.kind, choice.product_id],
                                { corners: choice.corners, dry_run: true }
                            )
                          : this.applyEdges(edgeItemsFor(targetKeys), choice),
              }
            : undefined;
        // The demolition works of a surface or a side ("Afbouw").
        const selectionItemsFor = (targetKeys) => {
            const picked = new Set(targetKeys || []);
            return [
                { record_id: targetIds[0], side: sideNumber, quantity },
                ...others
                    .filter((item) => picked.has(item.key))
                    .map((item) => ({
                        record_id: recordByShape[item.shapeId],
                        side: item.sideNumber,
                        quantity: item.quantity,
                    })),
            ].filter((item) => item.record_id);
        };
        const demolition = (isSurface || (hit.type === "edge" && !isObject)) && !isSeamHit
            ? {
                  projectId: record.resId,
                  scope: isSurface ? "surface" : "edge",
                  apply: (productIds, optionIds, targetKeys) =>
                      this.applySelection(
                          selectionItemsFor(targetKeys), coverage, productIds, optionIds, linkField
                      ),
              }
            : undefined;
        this.dialog.add(RoofProductPickerDialog, {
            title: _t("Producten toewijzen aan %s", target),
            domain: [
                ["sale_ok", "=", true],
                ["categ_id", "in", categoryIds],
            ],
            buildup,
            edges,
            demolition,
            assignedDomain: [
                [linkField, "=", targetIds[0]],
                ["coverage", "=", coverage],
                ["edge_index", "=", sideNumber],
            ],
            assignedLabel: isSeamHit
                ? _t("Reeds toegewezen aan deze naad")
                : isSurface
                ? _t("Reeds toegewezen aan dit oppervlak")
                : isCorner
                ? _t("Reeds toegewezen aan deze hoek")
                : sideNumber
                ? _t("Reeds toegewezen aan deze zijde")
                : _t("Reeds toegewezen aan deze omtrek"),
            quantity,
            targets: others,
            preselectedTargets: preselected,
            baseLabel: this.multiSelectLabel(hit),
            quantityUnit: isSurface ? " m²" : isCorner ? "" : " m",
            onConfirm: async (productIds, targetKeys) => {
                const picked = new Set(targetKeys || []);
                const items = [
                    {
                        recordId: targetIds[0],
                        sideNumber,
                        quantity,
                        label: target,
                    },
                    ...others
                        .filter((item) => picked.has(item.key))
                        .map((item) => ({
                            recordId: recordByShape[item.shapeId],
                            sideNumber: item.sideNumber,
                            quantity: item.quantity,
                            label: item.label,
                        })),
                ];
                try {
                    // Assigning to many items at once must not stack a second
                    // line on the ones that already have the product.
                    const existing = await this.orm.searchRead(
                        "tectora.roof.section.product",
                        [
                            [linkField, "in", items.map((item) => item.recordId)],
                            ["coverage", "=", coverage],
                        ],
                        [linkField, "edge_index", "product_id"]
                    );
                    const seen = new Set(
                        existing.map(
                            (line) =>
                                `${line[linkField][0]}|${line.edge_index}|` +
                                `${line.product_id[0]}`
                        )
                    );
                    const values = [];
                    for (const item of items) {
                        for (const productId of productIds) {
                            const key =
                                `${item.recordId}|${item.sideNumber}|${productId}`;
                            if (seen.has(key)) {
                                continue;
                            }
                            seen.add(key);
                            values.push({
                                [linkField]: item.recordId,
                                product_id: productId,
                                coverage,
                                edge_index: item.sideNumber,
                                quantity: item.quantity,
                            });
                        }
                    }
                    if (values.length) {
                        await this.orm.create(
                            "tectora.roof.section.product", values
                        );
                    }
                    await record.load();
                    const skipped =
                        items.length * productIds.length - values.length;
                    let message =
                        items.length > 1
                            ? _t(
                                  "%(lines)s lijn(en) toegewezen aan " +
                                  "%(items)s items.",
                                  { lines: values.length, items: items.length }
                              )
                            : _t("Product(en) toegewezen aan %s.", target);
                    if (skipped) {
                        message += " " + _t(
                            "%s koppeling(en) bestonden al en zijn " +
                            "overgeslagen.",
                            skipped
                        );
                    }
                    this.notification.add(message, {
                        type: values.length ? "success" : "warning",
                    });
                } catch (error) {
                    console.warn("Roof canvas: product assignment failed", error);
                    this.notification.add(
                        _t("Producten toewijzen is mislukt, probeer opnieuw."),
                        { type: "danger" }
                    );
                }
                this.draw();
                this.refreshPanel();
            },
        });
    }

    /** The "Randafwerking" of the picker: a roof edge (with its corners)
     * or a connection on the sides. */
    async applyEdges(items, choice) {
        const record = this.props.record;
        if (choice.geometry) {
            this.setSidesGeometry(items, choice.geometry);
            // Saved before the products go on, so the two do not cross.
            await record.save();
        }
        if (!choice.product_id) {
            this.notification.add(
                _t("Breedte en opstand gezet op %s zijde(n).", items.length),
                { type: "success" }
            );
            return;
        }
        try {
            const result = await this.orm.call(
                "tectora.roof.project", "tectora_apply_edges",
                [[record.resId], items, choice.kind, choice.product_id],
                { corners: choice.corners }
            );
            await record.load();
            let message = _t("Randafwerking toegepast op %s zijde(n).", result.lines);
            const corners = result.corners || {};
            if (corners.inner || corners.outer) {
                message += " " + _t("%(inner)s binnenhoek(en) en %(outer)s buitenhoek(en) toegevoegd.", {
                    inner: corners.inner || 0,
                    outer: corners.outer || 0,
                });
            }
            this.notification.add(message, { type: "success" });
            if ((result.missing || []).length) {
                this.notification.add(
                    _t("Geen passende %s gevonden voor deze dakrand: voeg die hoek(en) apart toe.",
                        result.missing.join(" / ")),
                    { type: "warning" }
                );
            }
        } catch (error) {
            console.warn("Roof canvas: applying the edge finish failed", error);
            this.notification.add(_t("Randafwerking toepassen is mislukt, probeer opnieuw."), {
                type: "danger",
            });
        }
        this.draw();
        this.refreshPanel();
    }

    /** The "Afbouw" of the picker: exactly the ticked works on the items. */
    async applySelection(items, coverage, productIds, optionIds, linkField) {
        const record = this.props.record;
        try {
            const result = await this.orm.call(
                "tectora.roof.project", "tectora_apply_selection",
                [[record.resId], items, coverage, productIds, optionIds],
                { link_field: linkField }
            );
            await record.load();
            this.notification.add(
                _t("Afbouw bijgewerkt: %(added)s toegevoegd, %(removed)s verwijderd.", {
                    added: result.added,
                    removed: result.removed,
                }),
                { type: "success" }
            );
        } catch (error) {
            console.warn("Roof canvas: applying the demolition failed", error);
            this.notification.add(_t("Afbouw toepassen is mislukt, probeer opnieuw."), {
                type: "danger",
            });
        }
        this.draw();
        this.refreshPanel();
    }

    /** Width (dakrand) and upstand (opstand) of the sides, in metres, as
     * the side panel sets them one side at a time. */
    setSidesGeometry(items, geometry) {
        const set = (shape, key, index, value) => {
            const values = { ...(shape[key] || {}) };
            if (value > 0) {
                values[index] = Math.round(value * 1000) / 1000;
            } else {
                delete values[index];
            }
            if (Object.keys(values).length) {
                shape[key] = values;
            } else {
                delete shape[key];
            }
        };
        for (const item of items) {
            const shape = this.shapes.find((s) => s.id === item.shape_id);
            if (!shape || !item.side) {
                continue;
            }
            if (geometry.width !== null && geometry.width !== undefined) {
                set(shape, "edgeWidths", item.side - 1, geometry.width);
            }
            if (geometry.upstand !== null && geometry.upstand !== undefined) {
                set(shape, "edgeUpstands", item.side - 1, geometry.upstand);
            }
        }
        this.commit();
        this.refreshPanel();
    }

    /** The "Dakopbouw" of the picker: the layers on the surfaces, and their
     * EPDM sheets. */
    async applyBuildup(sectionIds, choice) {
        const record = this.props.record;
        try {
            const result = await this.orm.call(
                "tectora.roof.project", "tectora_apply_buildup",
                [[record.resId], sectionIds],
                {
                    vapour_id: choice.vapour_id,
                    insulation_id: choice.insulation_id,
                    membrane_id: choice.membrane_id,
                    sheets: choice.sheets,
                    margin: choice.margin,
                    seam_overlap: choice.seam_overlap,
                }
            );
            await record.load();
            let message = _t("Dakopbouw toegepast op %s dakvlak(ken).", sectionIds.length);
            if (choice.sheets) {
                const sheets = result.sheets || [];
                const area = sheets.reduce((sum, sheet) => sum + sheet.area, 0);
                message += " " + _t("%(count)s EPDM-doek(en) berekend, samen %(area)s m² (tab Werf).", {
                    count: sheets.length,
                    area: area.toFixed(2),
                });
            }
            this.notification.add(message, { type: "success" });
        } catch (error) {
            console.warn("Roof canvas: applying the build-up failed", error);
            this.notification.add(_t("Dakopbouw toepassen is mislukt, probeer opnieuw."), {
                type: "danger",
            });
        }
        this.draw();
        this.refreshPanel();
    }

    measurements(points) {
        const scale = this.scaleMPerPx;
        const box = boundingBox(points);
        return {
            width: box.w * scale,
            length: box.h * scale,
            area: polygonArea(points) * scale * scale,
            perimeter: polygonPerimeter(points) * scale,
        };
    }

    // Inner polygon (canvas px) of a shape whose sides carry a width (m),
    // or null when no widths are set or the inset degenerates.
    innerPolygon(shape) {
        if (shape.shape === "circle" || !shape.edgeWidths) {
            return null;
        }
        const scale = this.scaleMPerPx;
        const n = shape.points.length;
        const widths = [];
        let hasWidth = false;
        for (let i = 0; i < n; i++) {
            const meters = parseFloat(shape.edgeWidths[i]) || 0;
            widths.push(meters > 0 ? meters / scale : 0);
            hasWidth = hasWidth || meters > 0;
        }
        return hasWidth ? insetPolygon(shape.points, widths) : null;
    }

    // A side's name: the one given in the side panel, else "Z1", "Z2", ...
    edgeName(shape, edgeIndex) {
        const name = shape.edgeNames && shape.edgeNames[edgeIndex];
        return (name && String(name).trim()) || `Z${edgeIndex + 1}`;
    }

    edgeWidth(shape, edgeIndex) {
        const value = shape.edgeWidths && shape.edgeWidths[edgeIndex];
        return parseFloat(value) || 0;
    }

    // Vertical height of the upstand (opstand) at this side, in meters.
    edgeUpstand(shape, edgeIndex) {
        const value = shape.edgeUpstands && shape.edgeUpstands[edgeIndex];
        return parseFloat(value) || 0;
    }

    updateStatus() {
        const pending = this.state.multiSelect;
        if (pending.length) {
            const labels = pending.map((hit) => this.multiSelectLabel(hit));
            this.state.status =
                `${pending.length} geselecteerd: ${labels.join(", ")} — laat ` +
                `Ctrl los om producten toe te wijzen, Esc om te annuleren`;
            return;
        }
        if (this.draftPolygon) {
            this.state.status =
                this.state.tool === "seam"
                    ? `Naad: ${this.draftPolygon.length} punt(en) — klik op de andere zijde om de naad af te werken (of dubbelklik/Enter), Esc om te annuleren`
                    : `Polygoon: ${this.draftPolygon.length} punt(en) — dubbelklik of Enter om te sluiten, Esc om te annuleren`;
            return;
        }
        const shape = this.selectedShape;
        if (shape && isSeam(shape)) {
            const length = polygonPerimeter(shape.points, false) * this.scaleMPerPx;
            this.state.status =
                `${shape.name || "Naad"} — naad van ${length.toFixed(2)} m · ` +
                `geselecteerd: sleep om te verplaatsen, versleep een punt om de ` +
                `lijn aan te passen, klik op het label om de naad te beschrijven, ` +
                `dubbelklik erop om naadproducten toe te wijzen`;
        } else if (shape) {
            const m = this.measurements(shape.points);
            this.state.status =
                `${shape.name || "Naamloos"} — ${m.width.toFixed(2)} × ` +
                `${m.length.toFixed(2)} m, ${m.area.toFixed(2)} m², omtrek ` +
                `${m.perimeter.toFixed(2)} m · geselecteerd: sleep om te ` +
                `verplaatsen, versleep een hoekpunt om de vorm aan te passen, ` +
                `rechtsklik op een lengtelabel om de werkelijke maat in te ` +
                `geven, klik op een lengte- of oppervlaktelabel om die zijde of ` +
                `dat vlak te beschrijven (dubbelklik: producten toewijzen); ` +
                `naam, rand en opstand van een zijde stel je in het paneel ` +
                `rechts in na een klik op die zijde`;
        } else {
            this.state.status =
                "Teken secties met de rechthoek- of polygoontool; de meting " +
                "wordt automatisch bijgewerkt (bij een nieuw project: eerst " +
                "opslaan). Klik op een lengte- of oppervlaktelabel om die zijde " +
                "of dat vlak te selecteren: rechts beschrijf je de originele en " +
                "de toekomstige staat en zie je de producten. Dubbelklik op een " +
                "label of klik op een hoekpunt om producten toe te voegen (wit = " +
                "buitenhoek, oranje = binnenhoek). Rechtsklik op een lengtelabel om de " +
                "werkelijke maat in te geven en de tekening te kalibreren; " +
                "rechtsklik op de tekening om een dakobject toe te voegen. " +
                "Teken een naad (stippellijn tussen twee dakvlakken) met de " +
                "naadtool. Scroll om te zoomen, F of de knop Tekenmodus om " +
                "de tekening met de werkbalk en het paneel vast op het scherm " +
                "te zetten.";
        }
    }

    // -------------------------------------------------------------- drawing
    draw() {
        const canvas = this.canvasRef();
        if (!canvas) {
            return;
        }
        const ctx = canvas.getContext("2d");
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = "#e8edef";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.setTransform(
            this.view.zoom, 0, 0, this.view.zoom, this.view.x, this.view.y
        );

        // World bounds + background
        ctx.fillStyle = "#f6f8f9";
        ctx.fillRect(0, 0, this.world.w, this.world.h);
        if (this.backgroundImage && this.state.showBackground) {
            ctx.globalAlpha = this.state.backgroundOpacity;
            ctx.drawImage(this.backgroundImage, 0, 0);
            ctx.globalAlpha = 1;
        }
        ctx.strokeStyle = "#9db2b8";
        ctx.lineWidth = 1 / this.view.zoom;
        ctx.strokeRect(0, 0, this.world.w, this.world.h);

        if (this.state.showGrid) {
            this.drawGrid(ctx);
        }

        // Per-shape try/catch: one malformed shape must never blank the form.
        for (const shape of this.shapes) {
            try {
                this.drawShape(ctx, shape, shape.id === this.state.selectedId);
            } catch (error) {
                console.warn("Roof canvas: could not draw shape", shape, error);
            }
        }
        this.labelHits = [];
        for (const shape of this.shapes) {
            try {
                this.drawShapeLabels(ctx, shape);
            } catch (error) {
                console.warn("Roof canvas: could not label shape", shape, error);
            }
        }
        try {
            this.drawQuoteMarks(ctx);
        } catch (error) {
            console.warn("Roof canvas: could not draw the quotation colours", error);
        }
        try {
            this.drawSheetLabels(ctx);
        } catch (error) {
            console.warn("Roof canvas: could not label the EPDM sheets", error);
        }
        this.drawFocus(ctx);
        if (this.drag && this.drag.mode === "rect") {
            this.drawDraftRect(ctx);
        }
        if (this.draftPolygon) {
            this.drawDraftPolygon(ctx);
        }
    }

    drawGrid(ctx) {
        const zoom = this.view.zoom;
        const scale = this.scaleMPerPx;
        const screenPxPerMeter = zoom / scale;
        const step =
            GRID_STEPS_M.find((s) => s * screenPxPerMeter >= GRID_MIN_SCREEN_PX) ||
            GRID_STEPS_M[GRID_STEPS_M.length - 1];
        if (this.state.gridStep !== step) {
            this.state.gridStep = step;
        }
        const stepPx = step / scale;
        const cols = Math.floor(this.world.w / stepPx);
        const rows = Math.floor(this.world.h / stepPx);

        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, this.world.w, this.world.h);
        ctx.clip();
        ctx.lineWidth = 1 / zoom;
        for (let i = 1; i <= cols; i++) {
            const x = i * stepPx;
            ctx.strokeStyle = i % GRID_MAJOR_EVERY === 0
                ? "rgba(11, 78, 91, 0.30)"
                : "rgba(11, 78, 91, 0.12)";
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, this.world.h);
            ctx.stroke();
        }
        for (let j = 1; j <= rows; j++) {
            const y = j * stepPx;
            ctx.strokeStyle = j % GRID_MAJOR_EVERY === 0
                ? "rgba(11, 78, 91, 0.30)"
                : "rgba(11, 78, 91, 0.12)";
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(this.world.w, y);
            ctx.stroke();
        }

        // Meter labels along the top and left edges, on the major lines.
        const fontSize = 10 / zoom;
        ctx.font = `${fontSize}px sans-serif`;
        ctx.fillStyle = "rgba(11, 78, 91, 0.75)";
        ctx.textAlign = "left";
        const formatMeters = (m) => (step < 1 ? m.toFixed(1) : String(m)) + " m";
        for (let i = GRID_MAJOR_EVERY; i <= cols; i += GRID_MAJOR_EVERY) {
            ctx.fillText(formatMeters(i * step), i * stepPx + 3 / zoom, fontSize * 1.2);
        }
        for (let j = GRID_MAJOR_EVERY; j <= rows; j += GRID_MAJOR_EVERY) {
            ctx.fillText(formatMeters(j * step), 3 / zoom, j * stepPx - 3 / zoom);
        }
        ctx.restore();
    }

    drawShapeLabels(ctx, shape) {
        const zoom = this.view.zoom;
        const scale = this.scaleMPerPx;
        const style = KIND_STYLES[shape.kind] || KIND_STYLES.section;
        const points = shape.points;
        const n = points.length;
        const fontSize = 11 / zoom;
        const boxHeight = 16 / zoom;
        const padX = 5 / zoom;
        ctx.font = `600 ${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        if (isSeam(shape)) {
            this.drawSeamLabels(ctx, shape, { zoom, scale, fontSize, boxHeight, padX, style });
            ctx.textBaseline = "alphabetic";
            return;
        }

        // Clickable name box at the shape's center (assigns surface
        // products), with only the area as plain text underneath. A dakobject
        // (chimney, skylight) shows its name only: its measurements are in
        // the side panel once it is clicked, its handles once it is selected.
        const m = this.measurements(points);
        const bbox = boundingBox(points);
        const isObject = (shape.kind || "section") !== "section";
        const selected = shape.id === this.state.selectedId;
        {
            const title = isObject
                ? (shape.name || style.label || "Naamloos").trim()
                : (shape.name || "").trim() || "Naamloos";
            const width = ctx.measureText(title).width + padX * 2;
            const cx = bbox.x + bbox.w / 2;
            const cy = bbox.y + bbox.h / 2 - boxHeight * 0.2;
            const x = cx - width / 2;
            const y = cy - boxHeight / 2;
            this.drawLabelBox(
                ctx, title, x, y, width, boxHeight, style.stroke,
                this.isMultiSelected({
                    type: "surface", shapeId: shape.id, kind: shape.kind || "section",
                })
            );
            this.labelHits.push({
                type: "surface",
                shapeId: shape.id,
                kind: shape.kind || "section",
                name: shape.name || "",
                x,
                y,
                w: width,
                h: boxHeight,
                areaM2: m.area,
            });
            if (isObject) {
                // the name only
            } else {
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "#0b1f24";
            const innerPoints = this.innerPolygon(shape);
            const areaText = innerPoints
                ? `${m.area.toFixed(1)} m² · binnen ${(
                      polygonArea(innerPoints) * scale * scale
                  ).toFixed(1)} m²`
                : `${m.area.toFixed(1)} m²`;
            ctx.fillText(areaText, cx, cy + boxHeight * 1.1);
            ctx.font = `600 ${fontSize}px sans-serif`;
            }
        }
        if (isObject && !selected) {
            ctx.textBaseline = "alphabetic";
            return; // no lengths, and handles only once selected
        }

        if (shape.shape === "circle") {
            // One circumference label at the top plus a radius drag handle;
            // circles have no discrete edges or corners. A dakobject gets the
            // handle only.
            if (!isObject) {
            const label = `${m.perimeter.toFixed(2)} m`;
            const width = ctx.measureText(label).width + padX * 2;
            const cx = bbox.x + bbox.w / 2;
            const x = cx - width / 2;
            const y = bbox.y - boxHeight / 2;
            this.drawLabelBox(
                ctx, label, x, y, width, boxHeight, style.stroke,
                this.isMultiSelected({
                    type: "edge", shapeId: shape.id, kind: shape.kind || "section", edgeIndex: -1,
                })
            );
            this.labelHits.push({
                type: "edge",
                shapeId: shape.id,
                kind: shape.kind || "section",
                name: shape.name || "",
                edgeIndex: -1,
                x,
                y,
                w: width,
                h: boxHeight,
                lengthM: m.perimeter,
            });
            }
            const handleSize = 5 / zoom;
            const hx = bbox.x + bbox.w;
            const hy = bbox.y + bbox.h / 2;
            ctx.fillStyle = "#ffffff";
            ctx.strokeStyle = style.stroke;
            ctx.lineWidth = 1.5 / zoom;
            ctx.fillRect(hx - handleSize, hy - handleSize, handleSize * 2, handleSize * 2);
            ctx.strokeRect(hx - handleSize, hy - handleSize, handleSize * 2, handleSize * 2);
            this.labelHits.push({
                type: "radius",
                shapeId: shape.id,
                kind: shape.kind || "section",
                name: shape.name || "",
                edgeIndex: 0,
                x: hx - handleSize * 1.5,
                y: hy - handleSize * 1.5,
                w: handleSize * 3,
                h: handleSize * 3,
            });
            ctx.textBaseline = "alphabetic";
            return;
        }

        // Length box on every edge (not on a dakobject: name only).
        for (let i = 0; i < (isObject ? 0 : n); i++) {
            const [x1, y1] = points[i];
            const [x2, y2] = points[(i + 1) % n];
            const lengthPx = Math.hypot(x2 - x1, y2 - y1);
            if (lengthPx * zoom < EDGE_LABEL_MIN_SCREEN_PX) {
                continue;
            }
            const lengthM = lengthPx * scale;
            // Name and length; width, upstand and the rest of the side are
            // in the side panel once the side is clicked.
            const label = `${this.edgeName(shape, i)} · ${lengthM.toFixed(2)} m`;
            const width = ctx.measureText(label).width + padX * 2;
            const cx = (x1 + x2) / 2;
            const cy = (y1 + y2) / 2;
            const x = cx - width / 2;
            const y = cy - boxHeight / 2;
            const picked = this.isMultiSelected({
                type: "edge", shapeId: shape.id, kind: shape.kind || "section", edgeIndex: i,
            });
            if (picked) {
                // Trace the side too: the label alone is easy to lose on a
                // drawing with many of them.
                ctx.save();
                ctx.strokeStyle = MULTI_SELECT_STROKE;
                ctx.lineWidth = 4 / zoom;
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();
                ctx.restore();
            }
            this.drawLabelBox(
                ctx, label, x, y, width, boxHeight, style.stroke, picked
            );
            this.labelHits.push({
                type: "edge",
                shapeId: shape.id,
                kind: shape.kind || "section",
                name: shape.name || "",
                edgeIndex: i,
                x,
                y,
                w: width,
                h: boxHeight,
                lengthM,
            });
        }
        ctx.textBaseline = "alphabetic";

        // Corner markers: outer (convex) corners are white with the shape's
        // stroke color, inner (reflex) corners are filled amber.
        const cornerRadius = 5 / zoom;
        for (let i = 0; i < n; i++) {
            const [px, py] = points[i];
            const inner = isInnerCorner(points, i);
            const pickedCorner = this.isMultiSelected({
                type: "corner",
                shapeId: shape.id,
                kind: shape.kind || "section",
                edgeIndex: i,
                cornerType: inner ? "inner" : "outer",
            });
            ctx.beginPath();
            ctx.arc(
                px, py, pickedCorner ? cornerRadius * 1.4 : cornerRadius,
                0, Math.PI * 2
            );
            ctx.fillStyle = pickedCorner
                ? MULTI_SELECT_FILL
                : inner ? "#d97706" : "#ffffff";
            ctx.fill();
            ctx.strokeStyle = pickedCorner
                ? MULTI_SELECT_STROKE
                : inner ? "#92400e" : style.stroke;
            ctx.lineWidth = (pickedCorner ? 2.5 : 1.5) / zoom;
            ctx.stroke();
            const hitRadius = cornerRadius * 1.5;
            this.labelHits.push({
                type: "corner",
                cornerType: inner ? "inner" : "outer",
                shapeId: shape.id,
                kind: shape.kind || "section",
                name: shape.name || "",
                edgeIndex: i,
                x: px - hitRadius,
                y: py - hitRadius,
                w: hitRadius * 2,
                h: hitRadius * 2,
            });
        }
    }

    // A seam gets one clickable label halfway along it (assigns seam
    // products) and drag handles on its points.
    drawSeamLabels(ctx, shape, { zoom, scale, fontSize, boxHeight, padX, style }) {
        const points = shape.points;
        const lengthM = polygonPerimeter(points, false) * scale;
        const title = `${style.label}: ${shape.name || ""} · ${lengthM.toFixed(2)} m`.trim();
        const width = ctx.measureText(title).width + padX * 2;
        const [mx, my] = polylineMidpoint(points);
        const x = mx - width / 2;
        const y = my - boxHeight * 1.3;
        const picked = this.isMultiSelected({ type: "seam", shapeId: shape.id, kind: "seam" });
        this.drawLabelBox(ctx, title, x, y, width, boxHeight, style.stroke, picked);
        this.labelHits.push({
            type: "seam",
            shapeId: shape.id,
            kind: "seam",
            name: shape.name || "",
            edgeIndex: 0,
            x,
            y,
            w: width,
            h: boxHeight,
            lengthM,
        });
        const handleRadius = 5 / zoom;
        for (let i = 0; i < points.length; i++) {
            const [px, py] = points[i];
            ctx.beginPath();
            ctx.arc(px, py, handleRadius, 0, Math.PI * 2);
            ctx.fillStyle = "#ffffff";
            ctx.fill();
            ctx.strokeStyle = style.stroke;
            ctx.lineWidth = 1.5 / zoom;
            ctx.stroke();
            const hitRadius = handleRadius * 1.5;
            this.labelHits.push({
                type: "corner",
                cornerType: "outer",
                shapeId: shape.id,
                kind: "seam",
                name: shape.name || "",
                edgeIndex: i,
                x: px - hitRadius,
                y: py - hitRadius,
                w: hitRadius * 2,
                h: hitRadius * 2,
            });
        }
        ctx.font = `${fontSize}px sans-serif`;
    }

    drawLabelBox(ctx, label, x, y, width, height, strokeColor, selected = false) {
        const zoom = this.view.zoom;
        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(x, y, width, height, 3 / zoom);
        } else {
            ctx.rect(x, y, width, height);
        }
        ctx.fillStyle = selected
            ? MULTI_SELECT_FILL
            : "rgba(255, 255, 255, 0.92)";
        ctx.fill();
        ctx.strokeStyle = selected ? MULTI_SELECT_STROKE : strokeColor;
        ctx.lineWidth = (selected ? 2 : 1) / zoom;
        ctx.stroke();
        ctx.fillStyle = selected ? "#ffffff" : "#0b1f24";
        ctx.fillText(label, x + width / 2, y + height / 2);
    }

    // ------------------------------------------------------ dakobject iconen
    // A product category that can be used for dakobjecten may carry an icon;
    // the server says which category each dakobject takes it from
    // (project.canvas_icons), because the shapes themselves know nothing about
    // products.
    get iconCategories() {
        const raw = this.props.record.data.canvas_icons || "";
        if (raw !== this._iconRaw) {
            this._iconRaw = raw;
            try {
                this._iconMap = JSON.parse(raw || "{}") || {};
            } catch {
                this._iconMap = {};
            }
        }
        return this._iconMap;
    }

    iconImage(categoryId) {
        const cached = this.iconImages[categoryId];
        if (cached !== undefined) {
            return cached || null; // null: tried and failed, do not retry
        }
        this.iconImages[categoryId] = null;
        const image = new Image();
        image.onload = () => {
            if (this._destroyed) {
                return;
            }
            this.iconImages[categoryId] = image;
            this.draw();
        };
        image.onerror = () => {
            this.iconImages[categoryId] = null;
        };
        image.src = `/web/image/product.category/${categoryId}/tectora_canvas_icon`;
        return null;
    }

    drawShapeIcon(ctx, shape) {
        if ((shape.kind || "section") === "section") {
            return; // only dakobjecten carry an icon
        }
        const categoryId = this.iconCategories[shape.id];
        if (!categoryId) {
            return;
        }
        const image = this.iconImage(categoryId);
        if (!image || !image.naturalWidth) {
            return;
        }
        const box = boundingBox(shape.points);
        // Fit inside the shape, aspect kept, with room left for its outline.
        const room = Math.min(box.w, box.h) * ICON_FILL_RATIO;
        const scale = room / Math.max(image.naturalWidth, image.naturalHeight);
        const width = image.naturalWidth * scale;
        const height = image.naturalHeight * scale;
        ctx.save();
        ctx.globalAlpha = 0.95;
        try {
            ctx.drawImage(
                image,
                box.x + (box.w - width) / 2,
                box.y + (box.h - height) / 2,
                width,
                height
            );
        } catch (error) {
            console.warn("Roof canvas: could not draw the icon", error);
        }
        ctx.restore();
    }

    drawShape(ctx, shape, selected) {
        const style = KIND_STYLES[shape.kind] || KIND_STYLES.section;
        const points = shape.points;
        const isCircle = shape.shape === "circle";
        if (isSeam(shape)) {
            // Open dotted line: the two surfaces on either side are separate.
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; i++) {
                ctx.lineTo(points[i][0], points[i][1]);
            }
            ctx.setLineDash([3 / this.view.zoom, 5 / this.view.zoom]);
            ctx.lineCap = "round";
            ctx.strokeStyle = selected ? "#111827" : style.stroke;
            ctx.lineWidth = (selected ? 4 : 3) / this.view.zoom;
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.lineCap = "butt";
            return;
        }
        ctx.beginPath();
        if (isCircle) {
            const box = boundingBox(points);
            ctx.arc(
                box.x + box.w / 2,
                box.y + box.h / 2,
                Math.max(box.w, box.h) / 2,
                0,
                Math.PI * 2
            );
        } else {
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; i++) {
                ctx.lineTo(points[i][0], points[i][1]);
            }
            ctx.closePath();
        }
        ctx.fillStyle = style.fill;
        ctx.fill();
        ctx.strokeStyle = selected ? "#111827" : style.stroke;
        ctx.lineWidth = (selected ? 3 : 2) / this.view.zoom;
        ctx.stroke();

        this.drawShapeIcon(ctx, shape);

        // Sides with an upstand (opstand) get a heavier accented outline.
        if (!isCircle && shape.edgeUpstands) {
            const n = points.length;
            ctx.strokeStyle = "#7c3aed";
            ctx.lineWidth = 5 / this.view.zoom;
            ctx.lineCap = "round";
            for (let i = 0; i < n; i++) {
                if (!this.edgeUpstand(shape, i)) {
                    continue;
                }
                const [ax, ay] = points[i];
                const [bx, by] = points[(i + 1) % n];
                ctx.beginPath();
                ctx.moveTo(ax, ay);
                ctx.lineTo(bx, by);
                ctx.stroke();
            }
            ctx.lineCap = "butt";
        }

        // Dashed inner outline when sides carry a width (dakrand).
        const inner = this.innerPolygon(shape);
        if (inner) {
            ctx.beginPath();
            ctx.moveTo(inner[0][0], inner[0][1]);
            for (let i = 1; i < inner.length; i++) {
                ctx.lineTo(inner[i][0], inner[i][1]);
            }
            ctx.closePath();
            ctx.setLineDash([5 / this.view.zoom, 4 / this.view.zoom]);
            ctx.strokeStyle = style.stroke;
            ctx.lineWidth = 1.5 / this.view.zoom;
            ctx.stroke();
            ctx.setLineDash([]);
        }

        if (selected && !isCircle) {
            const r = 4 / this.view.zoom;
            ctx.fillStyle = "#ffffff";
            for (const [x, y] of points) {
                ctx.beginPath();
                ctx.arc(x, y, r, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
        }

        // The name and measurements are drawn in drawShapeLabels so they
        // stay on top of neighbouring shapes.
    }

    drawDraftRect(ctx) {
        const [x1, y1] = this.drag.start;
        const [x2, y2] = this.drag.current;
        ctx.setLineDash([6 / this.view.zoom, 4 / this.view.zoom]);
        ctx.strokeStyle = "#0a7483";
        ctx.lineWidth = 2 / this.view.zoom;
        ctx.strokeRect(
            Math.min(x1, x2),
            Math.min(y1, y2),
            Math.abs(x2 - x1),
            Math.abs(y2 - y1)
        );
        ctx.setLineDash([]);

        // Live dimensions: width along the top, length along the side, the
        // area in the middle.
        const scale = this.scaleMPerPx;
        const left = Math.min(x1, x2);
        const top = Math.min(y1, y2);
        const w = Math.abs(x2 - x1);
        const h = Math.abs(y2 - y1);
        if (w * this.view.zoom < 2 && h * this.view.zoom < 2) {
            return;
        }
        const gap = 12 / this.view.zoom;
        this.drawDimension(ctx, `${(w * scale).toFixed(2)} m`, left + w / 2, top - gap);
        this.drawDimension(ctx, `${(h * scale).toFixed(2)} m`, left + w + gap, top + h / 2, "start");
        this.drawDimension(
            ctx,
            `${(w * h * scale * scale).toFixed(2)} m²`,
            left + w / 2,
            top + h / 2,
            "center",
            true
        );
    }

    // The point the next corner would land on: the first corner when the
    // pointer is close enough to close the polygon.
    draftSnap(point) {
        const points = this.draftPolygon;
        if (this.state.tool === "seam") {
            return this.seamSnap(point).point;
        }
        if (this.state.tool !== "seam" && points.length >= 3) {
            const [fx, fy] = points[0];
            if (Math.hypot(point[0] - fx, point[1] - fy) <= CLOSE_SNAP_PX / this.view.zoom) {
                return [fx, fy];
            }
        }
        return point;
    }

    // A dimension label while drawing: a small box with the text, centred on
    // (x, y) or starting there ("start"). "strong" is the area/total.
    drawDimension(ctx, text, x, y, align = "center", strong = false) {
        const zoom = this.view.zoom;
        const fontSize = 11 / zoom;
        const height = 16 / zoom;
        const padX = 5 / zoom;
        ctx.font = `${strong ? 700 : 600} ${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const width = ctx.measureText(text).width + padX * 2;
        const left = align === "start" ? x : x - width / 2;
        if (strong) {
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(left, y - height / 2, width, height, 3 / zoom);
            } else {
                ctx.rect(left, y - height / 2, width, height);
            }
            ctx.fillStyle = "#0a7483";
            ctx.fill();
            ctx.fillStyle = "#ffffff";
            ctx.fillText(text, left + width / 2, y);
        } else {
            this.drawLabelBox(ctx, text, left, y - height / 2, width, height, "#0a7483");
        }
        ctx.textBaseline = "alphabetic";
    }

    // The length of a side while drawing, at its middle; skipped when the
    // side is too short on screen to carry it.
    drawDraftEdge(ctx, [ax, ay], [bx, by]) {
        const length = Math.hypot(bx - ax, by - ay);
        if (length * this.view.zoom < EDGE_LABEL_MIN_SCREEN_PX) {
            return;
        }
        this.drawDimension(
            ctx, `${(length * this.scaleMPerPx).toFixed(2)} m`, (ax + bx) / 2, (ay + by) / 2
        );
    }

    drawDraftPolygon(ctx) {
        const points = this.draftPolygon;
        const cursor = this.draftCursor;
        const isSeamTool = this.state.tool === "seam";
        ctx.setLineDash([6 / this.view.zoom, 4 / this.view.zoom]);
        ctx.strokeStyle = "#0a7483";
        ctx.lineWidth = 2 / this.view.zoom;
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i][0], points[i][1]);
        }
        if (cursor) {
            ctx.lineTo(cursor[0], cursor[1]);
        }
        ctx.stroke();
        if (cursor && !isSeamTool && points.length >= 2) {
            // Where the polygon would close, faintly.
            ctx.globalAlpha = 0.35;
            ctx.beginPath();
            ctx.moveTo(cursor[0], cursor[1]);
            ctx.lineTo(points[0][0], points[0][1]);
            ctx.stroke();
            ctx.globalAlpha = 1;
        }
        ctx.setLineDash([]);
        const r = 4 / this.view.zoom;
        ctx.fillStyle = "#0a7483";
        for (const [x, y] of points) {
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        }

        // Live dimensions: every side drawn so far and the one following the
        // pointer; from three corners on, the area and perimeter the polygon
        // would have if closed now (for a seam, its length so far).
        const all = cursor ? [...points, cursor] : points;
        for (let i = 1; i < all.length; i++) {
            this.drawDraftEdge(ctx, all[i - 1], all[i]);
        }
        const scale = this.scaleMPerPx;
        const box = boundingBox(all);
        const below = box.y + box.h + 18 / this.view.zoom;
        if (isSeamTool) {
            if (all.length >= 2) {
                const length = polygonPerimeter(all, false) * scale;
                this.drawDimension(
                    ctx, `naad ${length.toFixed(2)} m`, box.x + box.w / 2, below, "center", true
                );
            }
        } else if (all.length >= 3) {
            const area = polygonArea(all) * scale * scale;
            const perimeter = polygonPerimeter(all) * scale;
            this.drawDimension(
                ctx,
                `${area.toFixed(2)} m² · omtrek ${perimeter.toFixed(2)} m`,
                box.x + box.w / 2,
                below,
                "center",
                true
            );
        }
    }
}

export const roofCanvasField = {
    component: RoofCanvasField,
    supportedTypes: ["text"],
    displayName: "Roof drawing canvas",
};

registry.category("fields").add("roof_canvas", roofCanvasField);
