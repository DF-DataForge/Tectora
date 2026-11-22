/** @odoo-module **/

/**
 * The plan document: the mirror of lib/document.py. See there for the format.
 * No Odoo import.
 */

export const SCHEMA = 1;
export const GROUPS = ["walls", "ceilings", "floors", "woodwork", "objects"];
export const OPENING_KINDS = ["door", "window", "passage", "exclusion"];
export const ITEM_KINDS = ["radiator", "custom"];
export const DEFAULT_HEIGHT = 2600;
const ROOM_HAS = { ceiling: true, floor: false, skirting: true, moulding: false };

export class DocumentError extends Error {}

export function emptyDocument() {
    return {
        schema: SCHEMA,
        units: "mm",
        seq: 1,
        defaults: { height: DEFAULT_HEIGHT, assign: {} },
        levels: [{ id: "L1", name: "Gelijkvloers", elevation: 0, rooms: [] }],
    };
}

function integer(value, fallback = 0) {
    const number = parseFloat(value);
    // halves away from zero would differ from Python's round only on exact
    // halves of a millimetre, which a drawing never has
    return Number.isFinite(number) ? Math.round(number) : fallback;
}

function number(value, fallback = 0) {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

function entries(value) {
    const result = [];
    for (const entry of Array.isArray(value) ? value : []) {
        if (!isObject(entry)) {
            continue;
        }
        const system = integer(entry.system);
        if (system > 0) {
            result.push({ system, colour: integer(entry.colour) || false });
        }
    }
    return result;
}

function assign(value) {
    const result = {};
    if (isObject(value)) {
        for (const [key, list] of Object.entries(value)) {
            result[String(key)] = entries(list);
        }
    }
    return result;
}

function opening(raw) {
    const kind = OPENING_KINDS.includes(raw.kind) ? raw.kind : "door";
    return {
        id: String(raw.id || ""),
        wall: String(raw.wall || ""),
        type: integer(raw.type) || false,
        kind,
        name: raw.name || "",
        offset: Math.max(integer(raw.offset), 0),
        width: Math.max(integer(raw.width), 0),
        height: Math.max(integer(raw.height), 0),
        sill: Math.max(integer(raw.sill), 0),
        reveal: Math.max(integer(raw.reveal), 0),
        reveal_sill: Boolean(raw.reveal_sill),
        leaf: Boolean(raw.leaf) && kind === "door",
        leaf_sides: integer(raw.leaf_sides, 2) === 1 ? 1 : 2,
        leaf_factor: number(raw.leaf_factor, 1) || 1,
        frame: Boolean(raw.frame) && (kind === "door" || kind === "window"),
        frame_girth: Math.max(integer(raw.frame_girth, 150), 0),
        pair: String(raw.pair || "") || false,
    };
}

function item(raw) {
    const kind = ITEM_KINDS.includes(raw.kind) ? raw.kind : "custom";
    const group = GROUPS.includes(raw.group) ? raw.group : "objects";
    return {
        id: String(raw.id || ""),
        type: integer(raw.type) || false,
        kind,
        group: kind === "radiator" ? "objects" : group,
        name: raw.name || "",
        wall: String(raw.wall || "") || false,
        offset: Math.max(integer(raw.offset), 0),
        width: Math.max(integer(raw.width), 0),
        height: Math.max(integer(raw.height), 0),
        length: Math.max(integer(raw.length), 0),
        count: Math.max(integer(raw.count, 1), 1),
        factor: number(raw.factor, 1) || 1,
        area: Math.max(number(raw.area), 0),
    };
}

function room(raw, defaultHeight) {
    const points = [];
    for (const point of raw.points || []) {
        if (Array.isArray(point) && point.length >= 2) {
            points.push([integer(point[0]), integer(point[1])]);
        }
    }
    const walls = [];
    const rawWalls = raw.walls || [];
    for (let index = 0; index < points.length; index++) {
        const wall = isObject(rawWalls[index]) ? rawWalls[index] : {};
        let heights = wall.h;
        if (Array.isArray(heights) && heights.length === 2) {
            heights = [Math.max(integer(heights[0]), 0), Math.max(integer(heights[1]), 0)];
        } else {
            heights = null;
        }
        walls.push({
            id: String(wall.id || ""),
            name: wall.name || "",
            virtual: Boolean(wall.virtual),
            h: heights,
        });
    }
    const has = { ...ROOM_HAS };
    for (const key of Object.keys(has)) {
        if (raw.has && key in raw.has) {
            has[key] = Boolean(raw.has[key]);
        }
    }
    const wallIds = new Set(walls.map((wall) => wall.id));
    const slopes = [];
    for (const slope of raw.slopes || []) {
        if (isObject(slope) && wallIds.has(String(slope.wall || ""))) {
            slopes.push({
                id: String(slope.id || ""),
                wall: String(slope.wall),
                knee: Math.max(integer(slope.knee), 0),
                pitch: Math.min(Math.max(number(slope.pitch, 45), 1), 89),
            });
        }
    }
    return {
        id: String(raw.id || ""),
        name: raw.name || "",
        height: Math.max(integer(raw.height, defaultHeight), 0) || defaultHeight,
        points,
        walls,
        slopes,
        openings: (raw.openings || [])
            .filter((o) => isObject(o) && wallIds.has(String(o.wall || "")))
            .map(opening),
        items: (raw.items || []).filter(isObject).map(item),
        has,
        skirting_height: Math.max(integer(raw.skirting_height, 70), 0),
        moulding_girth: Math.max(integer(raw.moulding_girth, 100), 0),
        assign: assign(raw.assign),
    };
}

export function load(text) {
    if (!text) {
        return emptyDocument();
    }
    let raw;
    if (isObject(text)) {
        raw = JSON.parse(JSON.stringify(text));
    } else {
        try {
            raw = JSON.parse(text);
        } catch {
            throw new DocumentError("Plan document is not valid JSON");
        }
    }
    if (!isObject(raw)) {
        throw new DocumentError("Plan document is not an object");
    }
    if (integer(raw.schema, SCHEMA) > SCHEMA) {
        throw new DocumentError(`Plan document of a newer version (${raw.schema})`);
    }
    const defaults = isObject(raw.defaults) ? raw.defaults : {};
    const defaultHeight = Math.max(integer(defaults.height, DEFAULT_HEIGHT), 0) || DEFAULT_HEIGHT;
    const defaultAssign = {};
    for (const [group, list] of Object.entries(assign(defaults.assign))) {
        if (GROUPS.includes(group)) {
            defaultAssign[group] = list;
        }
    }
    const document = {
        schema: SCHEMA,
        units: "mm",
        seq: Math.max(integer(raw.seq, 1), 1),
        defaults: { height: defaultHeight, assign: defaultAssign },
        levels: [],
    };
    for (const level of raw.levels || []) {
        if (!isObject(level)) {
            continue;
        }
        const entry = {
            id: String(level.id || ""),
            name: level.name || "",
            elevation: integer(level.elevation),
            rooms: (level.rooms || []).filter(isObject).map((r) => room(r, defaultHeight)),
        };
        if (isObject(level.background)) {
            entry.background = level.background;
        }
        document.levels.push(entry);
    }
    if (!document.levels.length) {
        document.levels = emptyDocument().levels;
    }
    completeIds(document);
    return document;
}

function completeIds(document) {
    const seen = new Set();
    const claim = (part, prefix, renamed) => {
        const previous = part.id;
        if (!previous || seen.has(previous)) {
            part.id = newId(document, prefix, seen);
            if (previous && !(previous in renamed)) {
                renamed[previous] = part.id;
            }
        }
        seen.add(part.id);
    };
    for (const level of document.levels) {
        claim(level, "L", {});
        for (const room of level.rooms) {
            const renamed = {};
            claim(room, "R", renamed);
            room.walls.forEach((wall) => claim(wall, "W", renamed));
            room.slopes.forEach((slope) => claim(slope, "S", renamed));
            room.openings.forEach((opening) => claim(opening, "O", renamed));
            room.items.forEach((item) => claim(item, "I", renamed));
            if (!Object.keys(renamed).length) {
                continue;
            }
            for (const part of [...room.slopes, ...room.openings, ...room.items]) {
                if (part.wall in renamed) {
                    part.wall = renamed[part.wall];
                }
            }
            const assign = {};
            for (const [key, list] of Object.entries(room.assign)) {
                const moved = key.split(":").map((token) => renamed[token] || token).join(":");
                assign[moved] = list;
            }
            room.assign = assign;
        }
    }
}

export function newId(document, prefix, taken = new Set()) {
    for (;;) {
        document.seq += 1;
        const candidate = `${prefix}${document.seq}`;
        if (!taken.has(candidate)) {
            return candidate;
        }
    }
}

export function dump(document) {
    return JSON.stringify(document);
}

/** [[level, room], ...] for every room of the document. (A plain list, not
 *  a generator: Odoo's module loader does not know `export function*`.) */
export function iterRooms(document) {
    const rooms = [];
    for (const level of document.levels) {
        for (const room of level.rooms) {
            rooms.push([level, room]);
        }
    }
    return rooms;
}
