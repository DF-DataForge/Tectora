/** @odoo-module **/

/**
 * From a plan document to the surfaces a painter paints: the mirror of
 * lib/measure.py, function by function. See there for what is measured how.
 * The document is in millimetres, everything returned here in metres.
 */

import * as geometry from "./geometry";
import { iterRooms } from "./document";

export const MM = 0.001;
const TOLERANCE = 1e-7;

export const KIND_GROUP = {
    wall: "walls",
    ceiling: "ceilings",
    slope: "ceilings",
    floor: "floors",
    skirting: "woodwork",
    moulding: "woodwork",
    frame: "woodwork",
    door_leaf: "woodwork",
    radiator: "objects",
};

export const KIND_LABEL = {
    wall: "Muur",
    ceiling: "Plafond",
    slope: "Schuin plafond",
    floor: "Vloer",
    skirting: "Plinten",
    moulding: "Kroonlijst",
    frame: "Omlijsting",
    door_leaf: "Deurblad",
    radiator: "Radiator",
    custom: "Vrij element",
};

export const OPENING_LABEL = {
    door: "Deur",
    window: "Raam",
    passage: "Doorgang",
    exclusion: "Uitsparing",
};

export function round2(value) {
    return Math.floor(value * 100 + 0.5 + 1e-9) / 100;
}

export class Ceiling {
    constructor(room) {
        this.points = room.points.map(([x, y]) => [x * MM, y * MM]);
        this.height = room.height * MM;
        this.slopes = [];
        const wallIndex = {};
        room.walls.forEach((wall, index) => {
            wallIndex[wall.id] = index;
        });
        for (const slope of room.slopes) {
            const index = wallIndex[slope.wall];
            const knee = slope.knee * MM;
            if (index === undefined || knee >= this.height - TOLERANCE) {
                continue;
            }
            const normal = geometry.inwardNormal(this.points, index);
            if (normal[0] === 0 && normal[1] === 0) {
                continue;
            }
            const origin = this.points[index];
            const radians = (slope.pitch * Math.PI) / 180;
            this.slopes.push({
                id: slope.id,
                knee,
                rise: Math.tan(radians),
                cos: Math.cos(radians),
                normal,
                offset: -(normal[0] * origin[0] + normal[1] * origin[1]),
            });
        }
    }

    /** [height, id of the slope that gives it or null] at a point. */
    at(point) {
        let height = this.height;
        let source = null;
        for (const slope of this.slopes) {
            const reach = slope.normal[0] * point[0] + slope.normal[1] * point[1] + slope.offset;
            if (reach < -TOLERANCE) {
                continue;
            }
            const value = slope.knee + slope.rise * Math.max(reach, 0);
            if (value < height - TOLERANCE) {
                height = value;
                source = slope.id;
            }
        }
        return [height, source];
    }

    lines() {
        const lines = [];
        for (const slope of this.slopes) {
            const [a, b] = slope.normal;
            lines.push([a, b, slope.offset]);
            lines.push([a, b, slope.offset - (this.height - slope.knee) / slope.rise]);
        }
        this.slopes.forEach((first, index) => {
            for (const second of this.slopes.slice(index + 1)) {
                const a = first.rise * first.normal[0] - second.rise * second.normal[0];
                const b = first.rise * first.normal[1] - second.rise * second.normal[1];
                if (Math.abs(a) < TOLERANCE && Math.abs(b) < TOLERANCE) {
                    continue;
                }
                const c =
                    first.knee + first.rise * first.offset - second.knee - second.rise * second.offset;
                lines.push([a, b, c]);
            }
        });
        return lines;
    }

    /** The floor cut along the lines the ceiling changes at. */
    pieces() {
        let pieces = [this.points];
        for (const line of this.lines()) {
            const cut = [];
            for (const piece of pieces) {
                for (const half of geometry.splitPolygon(piece, line)) {
                    if (half.length >= 3 && geometry.area(half) > TOLERANCE) {
                        cut.push(half);
                    }
                }
            }
            pieces = cut;
        }
        return pieces.map((piece) => ({
            points: piece,
            source: this.at(geometry.interiorPoint(piece))[1],
        }));
    }

    /** Map {slope id or null: plan area}. */
    parts() {
        const parts = new Map();
        for (const piece of this.pieces()) {
            parts.set(piece.source, (parts.get(piece.source) || 0) + geometry.area(piece.points));
        }
        return parts;
    }
}

export function wallProfile(room, ceiling, index) {
    const wall = room.walls[index];
    const start = ceiling.points[index];
    const end = ceiling.points[(index + 1) % ceiling.points.length];
    const length = geometry.distance(start, end);
    if (length < TOLERANCE) {
        return [];
    }
    if (wall.h) {
        return [[0, length, wall.h[0] * MM, wall.h[1] * MM]];
    }
    const cutSet = new Set([0, 1]);
    for (const line of ceiling.lines()) {
        const ratio = geometry.segmentLineCrossing(start, end, line);
        if (ratio !== null) {
            cutSet.add(ratio);
        }
    }
    const cuts = [...cutSet].sort((a, b) => a - b);
    const normal = geometry.inwardNormal(ceiling.points, index);
    const heightAt = (ratio) => {
        const point = [
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
        ];
        return ceiling.at([point[0] + normal[0] * 1e-6, point[1] + normal[1] * 1e-6])[0];
    };
    const profile = [];
    for (let i = 0; i + 1 < cuts.length; i++) {
        const first = cuts[i];
        const second = cuts[i + 1];
        if (second - first < TOLERANCE) {
            continue;
        }
        const quarter = heightAt(first + (second - first) * 0.25);
        const threeQuarters = heightAt(first + (second - first) * 0.75);
        const slope = (threeQuarters - quarter) * 2;
        profile.push([
            first * length,
            second * length,
            quarter - slope * 0.25,
            threeQuarters + slope * 0.25,
        ]);
    }
    return profile;
}

function wallSizes(profile, openings, deductMinArea) {
    const spans = openings.map((opening) => {
        const start = opening.offset * MM;
        return {
            opening,
            start,
            end: start + opening.width * MM,
            bottom: opening.sill * MM,
            top: (opening.sill + opening.height) * MM,
            area: 0,
            height: 0,
        };
    });
    const sortNumbers = (values) => [...values].sort((a, b) => a - b);
    const pieces = [];
    for (const [start, end, low, high] of profile) {
        const cutSet = new Set([start, end]);
        for (const span of spans) {
            for (const edge of [span.start, span.end]) {
                if (start < edge && edge < end) {
                    cutSet.add(edge);
                }
            }
        }
        const cuts = sortNumbers(cutSet);
        for (let i = 0; i + 1 < cuts.length; i++) {
            const first = cuts[i];
            const second = cuts[i + 1];
            const firstHeight = low + ((high - low) * (first - start)) / (end - start);
            const secondHeight = low + ((high - low) * (second - start)) / (end - start);
            const innerSet = new Set([first, second]);
            for (const span of spans) {
                if (span.start <= first + TOLERANCE && span.end >= second - TOLERANCE) {
                    for (const level of [span.bottom, span.top]) {
                        if ((firstHeight - level) * (secondHeight - level) < 0) {
                            const ratio = (level - firstHeight) / (secondHeight - firstHeight);
                            innerSet.add(first + (second - first) * ratio);
                        }
                    }
                }
            }
            const inner = sortNumbers(innerSet);
            for (let j = 0; j + 1 < inner.length; j++) {
                const a = inner[j];
                const b = inner[j + 1];
                if (b - a < TOLERANCE) {
                    continue;
                }
                const middle = (a + b) / 2;
                const height =
                    firstHeight + ((secondHeight - firstHeight) * (middle - first)) / (second - first);
                pieces.push([a, b, Math.max(height, 0)]);
            }
        }
    }

    let gross = 0;
    for (const [a, b, height] of pieces) {
        gross += (b - a) * height;
        for (const span of spans) {
            if (span.start <= a + TOLERANCE && span.end >= b - TOLERANCE) {
                const visible = Math.max(Math.min(span.top, height) - span.bottom, 0);
                span.area += (b - a) * visible;
                span.height = Math.max(span.height, visible);
            }
        }
    }
    const covered = (selection) => {
        let total = 0;
        for (const [a, b, height] of pieces) {
            const intervals = selection
                .filter((span) => span.start <= a + TOLERANCE && span.end >= b - TOLERANCE)
                .map((span) => [span.bottom, Math.min(span.top, height)]);
            total += (b - a) * geometry.unionLength(intervals);
        }
        return total;
    };
    const billed = spans.filter((span) => span.area >= deductMinArea - TOLERANCE);
    return {
        gross,
        openings: covered(spans),
        openings_billed: covered(billed),
        spans,
        height_max: Math.max(0, ...profile.map(([, , low, high]) => Math.max(low, high))),
    };
}

const ROUNDED = [
    "area_gross", "area_openings", "area_reveals", "area_net", "area_billed",
    "length", "paint_area", "height_max",
];

function surface(reference, room, level, kind, name, sizes = {}) {
    const result = {
        ref: reference,
        room: room.id,
        level: level.id,
        kind,
        group: sizes.group || KIND_GROUP[kind] || "objects",
        name,
        area_gross: 0,
        area_openings: 0,
        area_reveals: 0,
        area_net: 0,
        area_billed: 0,
        length: 0,
        count: 0,
        paint_area: 0,
        height_max: 0,
    };
    for (const [key, value] of Object.entries(sizes)) {
        if (key !== "group") {
            result[key] = value;
        }
    }
    for (const key of ROUNDED) {
        result[key] = round2(result[key]);
    }
    return result;
}

export function measureRoom(level, room, deductMinArea = 0) {
    if (room.points.length < 3) {
        return [];
    }
    const ceiling = new Ceiling(room);
    const surfaces = [];
    const prefix = room.id;
    let realLength = 0;
    let doorways = 0;
    let wallNumber = 0;

    room.walls.forEach((wall, index) => {
        if (wall.virtual) {
            return;
        }
        wallNumber += 1;
        const profile = wallProfile(room, ceiling, index);
        if (!profile.length) {
            return;
        }
        const length = profile[profile.length - 1][1];
        const lengthMm = Math.round(length / MM);
        const openings = room.openings.filter((o) => o.wall === wall.id);
        for (const opening of openings) {
            opening.offset = Math.min(opening.offset, lengthMm);
            opening.width = Math.min(opening.width, lengthMm - opening.offset);
        }
        const sizes = wallSizes(profile, openings, deductMinArea);
        let reveals = 0;
        for (const span of sizes.spans) {
            const opening = span.opening;
            if (opening.kind === "exclusion" || !opening.reveal) {
                continue;
            }
            let sides = 2 * span.height + opening.width * MM;
            if (opening.reveal_sill) {
                sides += opening.width * MM;
            }
            reveals += opening.reveal * MM * sides;
        }
        const net = Math.max(sizes.gross - sizes.openings, 0) + reveals;
        const billed = Math.max(sizes.gross - sizes.openings_billed, 0) + reveals;
        surfaces.push(
            surface(`${prefix}:wall:${wall.id}`, room, level, "wall",
                wall.name || `${KIND_LABEL.wall} ${wallNumber}`, {
                    area_gross: sizes.gross,
                    area_openings: sizes.openings,
                    area_reveals: reveals,
                    area_net: net,
                    area_billed: billed,
                    length,
                    paint_area: net,
                    height_max: sizes.height_max,
                })
        );
        realLength += length;
        doorways += geometry.unionLength(
            sizes.spans
                .filter((span) => !span.opening.sill && span.opening.kind !== "exclusion")
                .map((span) => [span.start, span.end])
        );

        for (const span of sizes.spans) {
            const opening = span.opening;
            const label = opening.name || OPENING_LABEL[opening.kind];
            const width = opening.width * MM;
            if (opening.frame) {
                let around = 2 * span.height + width;
                if (opening.kind === "window") {
                    around += width;
                }
                surfaces.push(
                    surface(`${opening.id}:frame`, room, level, "frame",
                        `${KIND_LABEL.frame} ${label.toLowerCase()}`, {
                            length: around,
                            count: 1,
                            paint_area: around * opening.frame_girth * MM,
                        })
                );
            }
            if (opening.leaf) {
                const faces =
                    width * opening.height * MM * opening.leaf_sides * opening.leaf_factor;
                surfaces.push(
                    surface(`${opening.id}:leaf`, room, level, "door_leaf",
                        `${KIND_LABEL.door_leaf} ${label.toLowerCase()}`, {
                            area_gross: faces,
                            area_net: faces,
                            area_billed: faces,
                            count: 1,
                            paint_area: faces,
                        })
                );
            }
        }
    });

    const floor = geometry.area(ceiling.points);
    const parts = ceiling.slopes.length ? ceiling.parts() : new Map([[null, floor]]);
    if (room.has.ceiling) {
        const flat = parts.get(null) || 0;
        if (flat > TOLERANCE) {
            surfaces.push(
                surface(`${prefix}:ceiling`, room, level, "ceiling", KIND_LABEL.ceiling, {
                    area_gross: flat,
                    area_net: flat,
                    area_billed: flat,
                    paint_area: flat,
                    height_max: ceiling.height,
                })
            );
        }
        ceiling.slopes.forEach((slope, index) => {
            const sloped = (parts.get(slope.id) || 0) / slope.cos;
            if (sloped > TOLERANCE) {
                surfaces.push(
                    surface(`${prefix}:slope:${slope.id}`, room, level, "slope",
                        `${KIND_LABEL.slope} ${index + 1}`, {
                            area_gross: sloped,
                            area_net: sloped,
                            area_billed: sloped,
                            paint_area: sloped,
                            height_max: ceiling.height,
                        })
                );
            }
        });
    }
    if (room.has.floor) {
        surfaces.push(
            surface(`${prefix}:floor`, room, level, "floor", KIND_LABEL.floor, {
                area_gross: floor,
                area_net: floor,
                area_billed: floor,
                paint_area: floor,
            })
        );
    }
    if (room.has.skirting && realLength - doorways > TOLERANCE) {
        const run = realLength - doorways;
        surfaces.push(
            surface(`${prefix}:skirting`, room, level, "skirting", KIND_LABEL.skirting, {
                length: run,
                paint_area: run * room.skirting_height * MM,
            })
        );
    }
    if (room.has.moulding && realLength > TOLERANCE) {
        surfaces.push(
            surface(`${prefix}:moulding`, room, level, "moulding", KIND_LABEL.moulding, {
                length: realLength,
                paint_area: realLength * room.moulding_girth * MM,
            })
        );
    }

    for (const item of room.items) {
        const count = item.count;
        if (item.kind === "radiator") {
            const faces = item.width * MM * item.height * MM * item.factor * count;
            surfaces.push(
                surface(item.id, room, level, "radiator", item.name || KIND_LABEL.radiator, {
                    area_gross: faces,
                    area_net: faces,
                    area_billed: faces,
                    count,
                    paint_area: faces,
                })
            );
        } else {
            const size = (item.area || item.width * MM * item.height * MM * item.factor) * count;
            surfaces.push(
                surface(item.id, room, level, "custom", item.name || KIND_LABEL.custom, {
                    group: item.group,
                    area_gross: size,
                    area_net: size,
                    area_billed: size,
                    length: item.length * MM * count,
                    count,
                    paint_area: size,
                })
            );
        }
    }
    return surfaces;
}

export function measureDocument(document, deductMinArea = 0) {
    const surfaces = [];
    const rooms = [];
    for (const [level, room] of iterRooms(document)) {
        const found = measureRoom(level, room, deductMinArea);
        surfaces.push(...found);
        const points = room.points.map(([x, y]) => [x * MM, y * MM]);
        const sum = (list, key) => list.reduce((total, s) => total + s[key], 0);
        rooms.push({
            ref: room.id,
            level: level.id,
            name: room.name,
            height: round2(room.height * MM),
            floor_area: points.length >= 3 ? round2(geometry.area(points)) : 0,
            perimeter: points.length >= 3 ? round2(geometry.perimeter(points)) : 0,
            wall_area: round2(sum(found.filter((s) => s.kind === "wall"), "area_net")),
            ceiling_area: round2(sum(found.filter((s) => s.group === "ceilings"), "area_net")),
        });
    }
    return { surfaces, rooms };
}

export function assignments(document, surfaces) {
    const explicit = {};
    for (const [, room] of iterRooms(document)) {
        Object.assign(explicit, room.assign);
    }
    const defaults = document.defaults.assign;
    const result = {};
    for (const item of surfaces) {
        const entries = item.ref in explicit ? explicit[item.ref] : defaults[item.group] || [];
        if (entries.length) {
            result[item.ref] = entries.map((entry) => ({ ...entry }));
        }
    }
    return result;
}

export function quantity(item, measure, billed = true) {
    if (measure === "m") {
        return item.length;
    }
    if (measure === "piece") {
        return item.count || 1;
    }
    if (["skirting", "moulding", "frame"].includes(item.kind)) {
        return item.paint_area;
    }
    return billed ? item.area_billed : item.area_net;
}

/** Map {"product|colour": {product, colour, quantity}}. */
export function materialNeeds(surfaces, assigned, systems) {
    const needs = new Map();
    for (const item of surfaces) {
        for (const entry of assigned[item.ref] || []) {
            const system = systems[entry.system];
            if (!system) {
                continue;
            }
            for (const layer of system.layers) {
                if (!layer.product || !layer.rate) {
                    continue;
                }
                const amount =
                    (item.paint_area * (layer.coats ?? 1) * (1 + (layer.waste || 0) / 100)) /
                    layer.rate /
                    (1 + (layer.dilution || 0) / 100);
                const colour = layer.tinted ? entry.colour || false : false;
                const key = `${layer.product}|${colour || 0}`;
                const current = needs.get(key) || { product: layer.product, colour, quantity: 0 };
                current.quantity += amount;
                needs.set(key, current);
            }
        }
    }
    return needs;
}
