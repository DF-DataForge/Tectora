/** @odoo-module **/

/**
 * Changing a plan document: every edit the editor makes, as a plain function
 * on the document, so it can be tested without a browser. Sizes in mm. No
 * Odoo import.
 */

import * as geometry from "./geometry";
import { newId } from "./document";

export function snap(value, step) {
    return step > 0 ? Math.round(value / step) * step : Math.round(value);
}

export function findRoom(document, roomId) {
    for (const level of document.levels) {
        const room = level.rooms.find((candidate) => candidate.id === roomId);
        if (room) {
            return { level, room };
        }
    }
    return null;
}

function nextName(level, base) {
    const taken = new Set(level.rooms.map((room) => room.name));
    for (let number = level.rooms.length + 1; ; number++) {
        const name = `${base} ${number}`;
        if (!taken.has(name)) {
            return name;
        }
    }
}

/** A new room with one wall per side. The points may run either way. */
export function addRoom(document, level, points, name = "") {
    const room = {
        id: newId(document, "R"),
        name: name || nextName(level, "Ruimte"),
        height: document.defaults.height,
        points: points.map(([x, y]) => [Math.round(x), Math.round(y)]),
        walls: [],
        slopes: [],
        openings: [],
        items: [],
        has: { ceiling: true, floor: false, skirting: true, moulding: false },
        skirting_height: 70,
        moulding_girth: 100,
        assign: {},
    };
    room.walls = room.points.map(() => ({
        id: newId(document, "W"), name: "", virtual: false, h: null,
    }));
    level.rooms.push(room);
    return room;
}

export function rectanglePoints(a, b) {
    const [x1, x2] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
    const [y1, y2] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
}

export function removeRoom(document, roomId) {
    for (const level of document.levels) {
        level.rooms = level.rooms.filter((room) => room.id !== roomId);
    }
}

/** A copy of a room with ids of its own, shifted so both are visible. */
export function duplicateRoom(document, level, room, shift = [500, 500]) {
    const copy = JSON.parse(JSON.stringify(room));
    const renamed = {};
    const claim = (part, prefix) => {
        const id = newId(document, prefix);
        renamed[part.id] = id;
        part.id = id;
    };
    claim(copy, "R");
    copy.walls.forEach((wall) => claim(wall, "W"));
    copy.slopes.forEach((slope) => claim(slope, "S"));
    copy.openings.forEach((opening) => claim(opening, "O"));
    copy.items.forEach((item) => claim(item, "I"));
    for (const part of [...copy.slopes, ...copy.openings, ...copy.items]) {
        if (part.wall in renamed) {
            part.wall = renamed[part.wall];
        }
        if (part.pair) {
            part.pair = false;
        }
    }
    const assign = {};
    for (const [key, list] of Object.entries(copy.assign)) {
        assign[key.split(":").map((token) => renamed[token] || token).join(":")] = list;
    }
    copy.assign = assign;
    copy.points = copy.points.map(([x, y]) => [x + shift[0], y + shift[1]]);
    copy.name = nextName(level, room.name.replace(/ \d+$/, "") || "Ruimte");
    level.rooms.push(copy);
    return copy;
}

export function moveRoom(room, dx, dy) {
    room.points = room.points.map(([x, y]) => [Math.round(x + dx), Math.round(y + dy)]);
}

/**
 * Give a wall another length. Everything at or beyond its far end moves with
 * it, so a rectangle stays a rectangle and an L keeps its shape.
 */
export function stretchWall(room, index, length) {
    const count = room.points.length;
    const start = room.points[index];
    const end = room.points[(index + 1) % count];
    const current = geometry.distance(start, end);
    if (current < 1 || length < 1) {
        return;
    }
    const direction = [(end[0] - start[0]) / current, (end[1] - start[1]) / current];
    const delta = length - current;
    const reach = (point) => (point[0] - start[0]) * direction[0] + (point[1] - start[1]) * direction[1];
    room.points = room.points.map((point) =>
        reach(point) >= current - 0.5
            ? [Math.round(point[0] + direction[0] * delta), Math.round(point[1] + direction[1] * delta)]
            : point
    );
    clampOpenings(room);
}

export function moveCorner(room, index, point) {
    room.points[index] = [Math.round(point[0]), Math.round(point[1])];
    clampOpenings(room);
}

/** Openings and items never run past the end of their wall. */
export function clampOpenings(room) {
    const count = room.points.length;
    const lengths = {};
    room.walls.forEach((wall, index) => {
        lengths[wall.id] = Math.round(
            geometry.distance(room.points[index], room.points[(index + 1) % count])
        );
    });
    for (const part of [...room.openings, ...room.items]) {
        const length = lengths[part.wall];
        if (length === undefined) {
            continue;
        }
        part.width = Math.min(part.width, length);
        part.offset = Math.max(Math.min(part.offset, length - part.width), 0);
    }
}

/**
 * A corner in a wall, at `offset` mm from its start. The first half keeps the
 * wall (its id, what is painted on it); the second half is a new wall that is
 * painted the same and takes the openings that lie on it.
 */
export function splitWall(document, room, index, offset) {
    const count = room.points.length;
    const start = room.points[index];
    const end = room.points[(index + 1) % count];
    const length = geometry.distance(start, end);
    if (offset < 10 || offset > length - 10) {
        return null;
    }
    const wall = room.walls[index];
    const ratio = offset / length;
    const corner = [
        Math.round(start[0] + (end[0] - start[0]) * ratio),
        Math.round(start[1] + (end[1] - start[1]) * ratio),
    ];
    const added = { id: newId(document, "W"), name: "", virtual: wall.virtual, h: null };
    if (wall.h) {
        const middle = Math.round(wall.h[0] + (wall.h[1] - wall.h[0]) * ratio);
        added.h = [middle, wall.h[1]];
        wall.h = [wall.h[0], middle];
    }
    room.points.splice(index + 1, 0, corner);
    room.walls.splice(index + 1, 0, added);
    for (const part of [...room.openings, ...room.items]) {
        if (part.wall === wall.id && part.offset >= offset) {
            part.wall = added.id;
            part.offset = Math.round(part.offset - offset);
        }
    }
    const key = `${room.id}:wall:${wall.id}`;
    if (key in room.assign) {
        room.assign[`${room.id}:wall:${added.id}`] = JSON.parse(JSON.stringify(room.assign[key]));
    }
    for (const slope of room.slopes.filter((candidate) => candidate.wall === wall.id)) {
        room.slopes.push({ ...slope, id: newId(document, "S"), wall: added.id });
    }
    clampOpenings(room);
    return added;
}

/** Take a corner out: the wall that started there goes, with what was on it. */
export function removeCorner(room, index) {
    if (room.points.length <= 3) {
        return false;
    }
    const wall = room.walls[index];
    room.points.splice(index, 1);
    room.walls.splice(index, 1);
    room.openings = room.openings.filter((opening) => opening.wall !== wall.id);
    room.items = room.items.filter((item) => item.wall !== wall.id);
    room.slopes = room.slopes.filter((slope) => slope.wall !== wall.id);
    delete room.assign[`${room.id}:wall:${wall.id}`];
    clampOpenings(room);
    return true;
}

const OPENING_DEFAULTS = {
    door: { width: 930, height: 2115, sill: 0, leaf: true, frame: true },
    window: { width: 1200, height: 1400, sill: 900, reveal: 150 },
    passage: { width: 1000, height: 2115, sill: 0 },
    exclusion: { width: 2000, height: 2000, sill: 0 },
};

/** A door, window, passage or exclusion on a wall, centred at `offset`. */
export function addOpening(document, room, wallId, preset, offset) {
    const index = room.walls.findIndex((wall) => wall.id === wallId);
    if (index < 0) {
        return null;
    }
    const kind = preset.kind in OPENING_DEFAULTS ? preset.kind : "door";
    const values = { ...OPENING_DEFAULTS[kind], ...preset };
    const length = Math.round(
        geometry.distance(room.points[index], room.points[(index + 1) % room.points.length])
    );
    const width = Math.min(Math.round(values.width || 900), length);
    const opening = {
        id: newId(document, "O"),
        wall: wallId,
        type: preset.id || false,
        kind,
        name: "",
        offset: Math.max(Math.min(Math.round(offset - width / 2), length - width), 0),
        width,
        height: Math.round(values.height || 2000),
        sill: Math.round(values.sill || 0),
        reveal: Math.round(values.reveal || 0),
        reveal_sill: false,
        leaf: Boolean(values.leaf) && kind === "door",
        leaf_sides: 2,
        leaf_factor: kind === "door" ? values.factor || 1 : 1,
        frame: Boolean(values.frame) && (kind === "door" || kind === "window"),
        frame_girth: Math.round(values.frame_girth || 150),
        pair: false,
    };
    room.openings.push(opening);
    return opening;
}

export function addRadiator(document, room, wallId, preset, offset) {
    const index = room.walls.findIndex((wall) => wall.id === wallId);
    const length = index < 0
        ? 0
        : Math.round(geometry.distance(room.points[index], room.points[(index + 1) % room.points.length]));
    const width = Math.min(Math.round(preset.width || 1000), length || 100000);
    const item = {
        id: newId(document, "I"),
        type: preset.id || false,
        kind: "radiator",
        group: "objects",
        name: "",
        wall: index < 0 ? false : wallId,
        offset: Math.max(Math.min(Math.round(offset - width / 2), length - width), 0),
        width,
        height: Math.round(preset.height || 600),
        length: 0,
        count: 1,
        factor: preset.factor || 2.5,
        area: 0,
    };
    room.items.push(item);
    return item;
}

export function addCustomItem(document, room) {
    const item = {
        id: newId(document, "I"), type: false, kind: "custom", group: "woodwork", name: "Vrij element",
        wall: false, offset: 0, width: 0, height: 0, length: 0, count: 1, factor: 1, area: 0,
    };
    room.items.push(item);
    return item;
}

/** The slope of a wall, made when it has none: knee 1 m, 45 degrees. */
export function toggleSlope(document, room, wallId) {
    const existing = room.slopes.find((slope) => slope.wall === wallId);
    if (existing) {
        room.slopes = room.slopes.filter((slope) => slope !== existing);
        delete room.assign[`${room.id}:slope:${existing.id}`];
        return null;
    }
    const slope = { id: newId(document, "S"), wall: wallId, knee: 1000, pitch: 45 };
    room.slopes.push(slope);
    return slope;
}

/** What is put on a surface: a list of entries, [] for nothing, or
 *  undefined to follow the project defaults again. */
export function setAssign(room, reference, entries) {
    if (entries === undefined) {
        delete room.assign[reference];
    } else {
        room.assign[reference] = entries.map((entry) => ({
            system: entry.system, colour: entry.colour || false,
        }));
    }
}

export function addLevel(document, name = "") {
    const last = document.levels[document.levels.length - 1];
    const height = last
        ? Math.max(document.defaults.height, ...last.rooms.map((room) => room.height))
        : 0;
    const level = {
        id: newId(document, "L"),
        name: name || `Verdieping ${document.levels.length}`,
        elevation: last ? last.elevation + height + 300 : 0,
        rooms: [],
    };
    document.levels.push(level);
    return level;
}

/** A level with the same rooms, to change into the floor above. */
export function copyLevel(document, source) {
    const level = addLevel(document);
    for (const room of source.rooms) {
        const copy = duplicateRoom(document, level, room, [0, 0]);
        copy.name = room.name;
    }
    return level;
}

export function removeLevel(document, levelId) {
    if (document.levels.length > 1) {
        document.levels = document.levels.filter((level) => level.id !== levelId);
    }
}

/**
 * Where a point being drawn should land: on a corner that is near, else in
 * line with one (same x or same y), else on the grid. The corners of
 * `skipRoom` (the room being changed) do not count.
 */
export function snapPoint(level, point, tolerance, step, skipRoom = null) {
    let [x, y] = point;
    let snappedX = false;
    let snappedY = false;
    let bestCorner = null;
    for (const room of level.rooms) {
        if (room.id === skipRoom) {
            continue;
        }
        for (const corner of room.points) {
            const d = geometry.distance(point, corner);
            if (d <= tolerance && (!bestCorner || d < bestCorner.d)) {
                bestCorner = { d, corner };
            }
            if (!snappedX && Math.abs(corner[0] - point[0]) <= tolerance) {
                x = corner[0];
                snappedX = true;
            }
            if (!snappedY && Math.abs(corner[1] - point[1]) <= tolerance) {
                y = corner[1];
                snappedY = true;
            }
        }
    }
    if (bestCorner) {
        return [bestCorner.corner[0], bestCorner.corner[1]];
    }
    return [snappedX ? x : snap(x, step), snappedY ? y : snap(y, step)];
}

/** The end of a side drawn from `origin` towards `point`: straight or at 45
 *  degrees, its length a whole number of steps. */
export function orthoPoint(origin, point, step, free = false) {
    const dx = point[0] - origin[0];
    const dy = point[1] - origin[1];
    const length = Math.hypot(dx, dy);
    if (free || length < 1) {
        return [snap(point[0], step), snap(point[1], step)];
    }
    const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
    const snapped = Math.max(snap(length, step), step);
    return [
        Math.round(origin[0] + Math.cos(angle) * snapped),
        Math.round(origin[1] + Math.sin(angle) * snapped),
    ];
}
