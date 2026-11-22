/** @odoo-module **/

/**
 * Drawing the plan of one level on a canvas, and finding what is under the
 * pointer. Plain functions: the editor component keeps the state and calls
 * these. World coordinates are millimetres, y pointing down as on the screen.
 */

import * as geometry from "./lib/geometry";
import { MM } from "./lib/measure";

export const COLOURS = {
    paper: "#ffffff",
    grid: "#eef1f4",
    gridStrong: "#dfe4ea",
    room: "#f3f5f8",
    roomSelected: "#e6eefb",
    wall: "#2b3440",
    wallVirtual: "#9aa5b1",
    selected: "#1f6fd6",
    window: "#4a90d9",
    exclusion: "#d98e2b",
    item: "#b25c3a",
    slope: "#6c7a89",
    text: "#1b2530",
    muted: "#6b7785",
    draft: "#1f6fd6",
};

export function toScreen(view, point) {
    return [(point[0] - view.x) * view.zoom, (point[1] - view.y) * view.zoom];
}

export function toWorld(view, point) {
    return [point[0] / view.zoom + view.x, point[1] / view.zoom + view.y];
}

/** The grid step in mm that suits the zoom: 10 cm, 50 cm, 1 m, 5 m. */
export function gridStep(view) {
    for (const step of [100, 500, 1000, 5000, 10000]) {
        if (step * view.zoom >= 14) {
            return step;
        }
    }
    return 50000;
}

export function formatMetres(mm) {
    return (mm * MM).toFixed(2).replace(".", ",");
}

function wallEnds(room, index) {
    return [room.points[index], room.points[(index + 1) % room.points.length]];
}

export function wallLength(room, index) {
    const [start, end] = wallEnds(room, index);
    return geometry.distance(start, end);
}

/** The point at `offset` mm along a wall. */
export function alongWall(room, index, offset) {
    const [start, end] = wallEnds(room, index);
    const length = geometry.distance(start, end) || 1;
    const ratio = offset / length;
    return [start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio];
}

function drawGrid(ctx, view, width, height) {
    const step = gridStep(view);
    const [left, top] = toWorld(view, [0, 0]);
    const [right, bottom] = toWorld(view, [width, height]);
    ctx.lineWidth = 1;
    for (let x = Math.floor(left / step) * step; x <= right; x += step) {
        const screen = Math.round((x - view.x) * view.zoom) + 0.5;
        ctx.strokeStyle = Math.round(x / step) % 5 === 0 ? COLOURS.gridStrong : COLOURS.grid;
        ctx.beginPath();
        ctx.moveTo(screen, 0);
        ctx.lineTo(screen, height);
        ctx.stroke();
    }
    for (let y = Math.floor(top / step) * step; y <= bottom; y += step) {
        const screen = Math.round((y - view.y) * view.zoom) + 0.5;
        ctx.strokeStyle = Math.round(y / step) % 5 === 0 ? COLOURS.gridStrong : COLOURS.grid;
        ctx.beginPath();
        ctx.moveTo(0, screen);
        ctx.lineTo(width, screen);
        ctx.stroke();
    }
}

function path(ctx, view, points, closed = true) {
    ctx.beginPath();
    points.forEach((point, index) => {
        const [x, y] = toScreen(view, point);
        if (index) {
            ctx.lineTo(x, y);
        } else {
            ctx.moveTo(x, y);
        }
    });
    if (closed) {
        ctx.closePath();
    }
}

function label(ctx, text, x, y, options = {}) {
    const lines = String(text).split("\n");
    ctx.font = `${options.bold ? "600 " : ""}${options.size || 12}px Inter, Arial, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const lineHeight = (options.size || 12) + 3;
    if (options.box) {
        const width = Math.max(...lines.map((line) => ctx.measureText(line).width)) + 8;
        const height = lines.length * lineHeight + 4;
        ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
        ctx.fillRect(x - width / 2, y - height / 2, width, height);
    }
    ctx.fillStyle = options.colour || COLOURS.text;
    lines.forEach((line, index) => {
        ctx.fillText(line, x, y + (index - (lines.length - 1) / 2) * lineHeight);
    });
}

/**
 * Draw one level.
 *
 * scene: {
 *   level, selection: {room, wall, opening, item}, hover: same shape,
 *   wallColour(room, wall) -> css colour or null, roomTint(room) -> css or null,
 *   roomAreas: {roomId: m2}, showGrid, showSizes,
 *   draft: {kind: "rect"|"polygon", points, cursor} or null,
 * }
 */
export function drawPlan(ctx, view, width, height, scene) {
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = COLOURS.paper;
    ctx.fillRect(0, 0, width, height);
    if (scene.showGrid) {
        drawGrid(ctx, view, width, height);
    }
    const selection = scene.selection || {};
    for (const room of scene.level.rooms) {
        if (room.points.length < 3) {
            continue;
        }
        const selected = selection.room === room.id;
        path(ctx, view, room.points);
        ctx.fillStyle = scene.roomTint(room) || (selected ? COLOURS.roomSelected : COLOURS.room);
        ctx.fill();
        if (selected) {
            ctx.strokeStyle = COLOURS.selected;
            ctx.lineWidth = 9;
            ctx.globalAlpha = 0.18;
            ctx.stroke();
            ctx.globalAlpha = 1;
        }

        // slopes: a hatch running from the wall they start at
        const metres = room.points.map(([x, y]) => [x * MM, y * MM]);
        for (const slope of room.slopes) {
            const index = room.walls.findIndex((wall) => wall.id === slope.wall);
            if (index < 0) {
                continue;
            }
            const normal = geometry.inwardNormal(metres, index);
            const reach = Math.max(
                (room.height - slope.knee) / Math.tan((slope.pitch * Math.PI) / 180), 0
            );
            const [start, end] = wallEnds(room, index);
            const far = [
                [start[0] + normal[0] * reach, start[1] + normal[1] * reach],
                [end[0] + normal[0] * reach, end[1] + normal[1] * reach],
            ];
            ctx.save();
            path(ctx, view, room.points);
            ctx.clip();
            ctx.strokeStyle = COLOURS.slope;
            ctx.lineWidth = 1;
            ctx.setLineDash([6, 4]);
            path(ctx, view, far, false);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.globalAlpha = 0.35;
            const steps = Math.max(Math.round((wallLength(room, index) * view.zoom) / 26), 2);
            for (let step = 1; step < steps; step++) {
                const ratio = step / steps;
                const from = [
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                ];
                const to = [from[0] + normal[0] * reach, from[1] + normal[1] * reach];
                path(ctx, view, [from, to], false);
                ctx.stroke();
            }
            ctx.restore();
        }

        // walls
        room.walls.forEach((wall, index) => {
            const [start, end] = wallEnds(room, index);
            const isSelected = selected && selection.wall === wall.id;
            const isHover = scene.hover && scene.hover.room === room.id && scene.hover.wall === wall.id;
            ctx.lineCap = "round";
            if (wall.virtual) {
                ctx.setLineDash([8, 6]);
                ctx.strokeStyle = isSelected ? COLOURS.selected : COLOURS.wallVirtual;
                ctx.lineWidth = 2;
            } else {
                ctx.strokeStyle = COLOURS.wall;
                ctx.lineWidth = 6;
            }
            path(ctx, view, [start, end], false);
            ctx.stroke();
            ctx.setLineDash([]);
            // the colour of the wall as a band on its inside
            const colour = !wall.virtual && scene.wallColour(room, wall);
            if (colour) {
                const normal = geometry.inwardNormal(metres, index);
                const shift = 6 / view.zoom;
                ctx.strokeStyle = colour;
                ctx.lineWidth = 5;
                ctx.lineCap = "butt";
                path(ctx, view, [
                    [start[0] + normal[0] * shift, start[1] + normal[1] * shift],
                    [end[0] + normal[0] * shift, end[1] + normal[1] * shift],
                ], false);
                ctx.stroke();
            }
            if (isSelected || isHover) {
                ctx.strokeStyle = COLOURS.selected;
                ctx.globalAlpha = isSelected ? 0.9 : 0.45;
                ctx.lineWidth = 3;
                path(ctx, view, [start, end], false);
                ctx.stroke();
                ctx.globalAlpha = 1;
            }
        });

        // openings: a gap in the wall, a window as a blue line, an exclusion orange
        for (const opening of room.openings) {
            const index = room.walls.findIndex((wall) => wall.id === opening.wall);
            if (index < 0) {
                continue;
            }
            const from = alongWall(room, index, opening.offset);
            const to = alongWall(room, index, opening.offset + opening.width);
            const isSelected = selection.opening === opening.id;
            ctx.lineCap = "butt";
            ctx.strokeStyle = COLOURS.paper;
            ctx.lineWidth = 7;
            path(ctx, view, [from, to], false);
            ctx.stroke();
            ctx.lineWidth = opening.kind === "window" ? 3 : 2;
            ctx.strokeStyle = isSelected
                ? COLOURS.selected
                : opening.kind === "window"
                  ? COLOURS.window
                  : opening.kind === "exclusion"
                    ? COLOURS.exclusion
                    : COLOURS.muted;
            if (opening.kind === "exclusion") {
                ctx.setLineDash([3, 3]);
            }
            path(ctx, view, [from, to], false);
            ctx.stroke();
            ctx.setLineDash([]);
            if (opening.kind === "door") {
                // the swing of the door, a quarter circle into the room
                const normal = geometry.inwardNormal(metres, index);
                const [sx, sy] = toScreen(view, from);
                const radius = opening.width * view.zoom;
                const base = Math.atan2(to[1] - from[1], to[0] - from[0]);
                const inward = Math.atan2(normal[1], normal[0]);
                let sweep = inward - base;
                while (sweep > Math.PI) {
                    sweep -= 2 * Math.PI;
                }
                while (sweep < -Math.PI) {
                    sweep += 2 * Math.PI;
                }
                ctx.strokeStyle = isSelected ? COLOURS.selected : COLOURS.muted;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(sx, sy, radius, base, base + sweep, sweep < 0);
                ctx.stroke();
            }
        }

        // items on a wall: a small block against it
        for (const item of room.items) {
            const index = room.walls.findIndex((wall) => wall.id === item.wall);
            if (index < 0 || !item.width) {
                continue;
            }
            const normal = geometry.inwardNormal(metres, index);
            const depth = 110;
            const from = alongWall(room, index, item.offset);
            const to = alongWall(room, index, item.offset + item.width);
            path(ctx, view, [
                from, to,
                [to[0] + normal[0] * depth, to[1] + normal[1] * depth],
                [from[0] + normal[0] * depth, from[1] + normal[1] * depth],
            ]);
            ctx.fillStyle = selection.item === item.id ? COLOURS.selected : COLOURS.item;
            ctx.globalAlpha = 0.75;
            ctx.fill();
            ctx.globalAlpha = 1;
        }

        // sizes along the walls
        if (scene.showSizes && view.zoom > 0.02) {
            room.walls.forEach((wall, index) => {
                const [start, end] = wallEnds(room, index);
                const length = geometry.distance(start, end);
                if (length * view.zoom < 46) {
                    return;
                }
                const normal = geometry.inwardNormal(metres, index);
                const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
                const [x, y] = toScreen(view, middle);
                label(ctx, formatMetres(length), x - normal[0] * 14, y - normal[1] * 14, {
                    size: 11, colour: COLOURS.muted, box: true,
                });
            });
        }

        // corners of the selected room, to drag
        if (selected) {
            for (const point of room.points) {
                const [x, y] = toScreen(view, point);
                ctx.fillStyle = COLOURS.paper;
                ctx.strokeStyle = COLOURS.selected;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(x, y, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
        }

        const [cx, cy] = toScreen(view, geometry.interiorPoint(room.points));
        const size = scene.roomAreas[room.id];
        label(
            ctx,
            `${room.name || "Ruimte"}\n${size === undefined ? "" : size.toFixed(2).replace(".", ",") + " m²"}`,
            cx, cy, { bold: true, size: 13 }
        );
    }

    const draft = scene.draft;
    if (draft && draft.points.length) {
        const points = draft.cursor ? [...draft.points, draft.cursor] : draft.points;
        ctx.strokeStyle = COLOURS.draft;
        ctx.fillStyle = "rgba(31, 111, 214, 0.08)";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        path(ctx, view, points, draft.kind === "rect");
        if (draft.kind === "rect" || points.length > 2) {
            ctx.fill();
        }
        ctx.stroke();
        ctx.setLineDash([]);
        for (let index = 0; index + 1 < points.length || (draft.kind === "rect" && index < points.length); index++) {
            const start = points[index];
            const end = points[(index + 1) % points.length];
            const length = geometry.distance(start, end);
            if (length * view.zoom < 30) {
                continue;
            }
            const [x, y] = toScreen(view, [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]);
            label(ctx, formatMetres(length), x, y - 12, { size: 11, colour: COLOURS.draft, box: true });
        }
        for (const point of draft.points) {
            const [x, y] = toScreen(view, point);
            ctx.fillStyle = COLOURS.draft;
            ctx.beginPath();
            ctx.arc(x, y, 3.5, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}

/**
 * What is at a world point of the level, nearest first:
 * {room, corner} | {room, opening} | {room, item} | {room, wall, offset} | {room} | null.
 * `tolerance` is in mm (a few screen pixels).
 */
export function hitTest(level, point, tolerance, selectedRoom = null) {
    // corners of the selected room first: they sit on top of its walls
    if (selectedRoom) {
        const room = level.rooms.find((candidate) => candidate.id === selectedRoom);
        if (room) {
            for (let index = 0; index < room.points.length; index++) {
                if (geometry.distance(point, room.points[index]) <= tolerance * 1.3) {
                    return { room: room.id, corner: index };
                }
            }
        }
    }
    let best = null;
    for (const room of [...level.rooms].reverse()) {
        if (room.points.length < 3) {
            continue;
        }
        for (let index = 0; index < room.walls.length; index++) {
            const [start, end] = wallEnds(room, index);
            const near = geometry.nearestOnSegment(point, start, end);
            if (near.distance > tolerance || (best && best.distance <= near.distance)) {
                continue;
            }
            const offset = near.ratio * geometry.distance(start, end);
            const wall = room.walls[index];
            const hit = { room: room.id, wall: wall.id, wallIndex: index, offset, distance: near.distance };
            for (const opening of room.openings) {
                if (opening.wall === wall.id && offset >= opening.offset && offset <= opening.offset + opening.width) {
                    hit.opening = opening.id;
                }
            }
            for (const item of room.items) {
                if (item.wall === wall.id && offset >= item.offset && offset <= item.offset + item.width) {
                    hit.item = item.id;
                }
            }
            best = hit;
        }
    }
    if (best) {
        return best;
    }
    for (const room of [...level.rooms].reverse()) {
        if (room.points.length >= 3 && geometry.pointInPolygon(point, room.points)) {
            return { room: room.id };
        }
    }
    return null;
}

/** The view that shows every room of the level with a margin. */
export function fitView(level, width, height) {
    const points = level.rooms.flatMap((room) => room.points);
    if (!points.length) {
        return { zoom: 0.08, x: -1500, y: -1500 };
    }
    const [minX, minY, maxX, maxY] = geometry.boundingBox(points);
    const margin = 70;
    const zoom = Math.min(
        (width - 2 * margin) / Math.max(maxX - minX, 1000),
        (height - 2 * margin) / Math.max(maxY - minY, 1000),
        0.25
    );
    return {
        zoom,
        x: (minX + maxX) / 2 - width / 2 / zoom,
        y: (minY + maxY) / 2 - height / 2 / zoom,
    };
}
