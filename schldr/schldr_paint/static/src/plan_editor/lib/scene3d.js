/** @odoo-module **/

/**
 * The plan as faces in space, for the 3D view: floors, walls with their top
 * line (straight, or following a sloped ceiling), doors and windows on the
 * walls, and the sloped ceilings. Metres, z up. No Odoo import: the renderer
 * (plan_3d.js) draws these on a canvas and could be replaced by another.
 */

import * as geometry from "./geometry";
import { Ceiling, MM, wallProfile } from "./measure";

const OPENING_COLOURS = {
    door: "#a67c52",
    window: "#bcd9f2",
    passage: "#5b6470",
    exclusion: "#d8c7a3",
};

/**
 * [{kind: "floor"|"wall"|"slope", points: [[x, y, z], ...], colour, normal: [nx, ny] (walls),
 *   decals: [{points, colour}]}]
 *
 * `colours` maps a surface reference to a css colour (what is painted there).
 */
export function buildScene(document, levelIds, colours = {}) {
    const faces = [];
    for (const level of document.levels) {
        if (levelIds && !levelIds.includes(level.id)) {
            continue;
        }
        const base = level.elevation * MM;
        for (const room of level.rooms) {
            if (room.points.length < 3) {
                continue;
            }
            const ceiling = new Ceiling(room);
            const plan = ceiling.points;
            faces.push({
                kind: "floor",
                points: plan.map(([x, y]) => [x, y, base]),
                colour: colours[`${room.id}:floor`] || "#e9e3d8",
            });
            room.walls.forEach((wall, index) => {
                if (wall.virtual) {
                    return;
                }
                const start = plan[index];
                const end = plan[(index + 1) % plan.length];
                const length = geometry.distance(start, end);
                const profile = wallProfile(room, ceiling, index);
                if (!profile.length) {
                    return;
                }
                const normal = geometry.inwardNormal(plan, index);
                const at = (offset) => [
                    start[0] + ((end[0] - start[0]) * offset) / length,
                    start[1] + ((end[1] - start[1]) * offset) / length,
                ];
                const heightAt = (offset) => {
                    for (const [a, b, low, high] of profile) {
                        if (offset >= a - 1e-9 && offset <= b + 1e-9) {
                            return low + ((high - low) * (offset - a)) / (b - a || 1);
                        }
                    }
                    return profile[profile.length - 1][3];
                };
                // one face per wall: along the floor, back along the top line
                const bottom = [at(0), at(length)].map(([x, y]) => [x, y, base]);
                const top = [];
                for (const [a, b, low, high] of profile) {
                    top.push([...at(a), base + low], [...at(b), base + high]);
                }
                const face = {
                    kind: "wall",
                    points: [...bottom, ...top.reverse()],
                    colour: colours[`${room.id}:wall:${wall.id}`] || "#f4f4f2",
                    normal,
                    decals: [],
                };
                for (const opening of room.openings.filter((o) => o.wall === wall.id)) {
                    const from = opening.offset * MM;
                    const to = Math.min((opening.offset + opening.width) * MM, length);
                    const low = opening.sill * MM;
                    const high = (opening.sill + opening.height) * MM;
                    const inset = ([x, y]) => [x + normal[0] * 0.02, y + normal[1] * 0.02];
                    const a = inset(at(from));
                    const b = inset(at(to));
                    face.decals.push({
                        points: [
                            [...a, base + low],
                            [...b, base + low],
                            [...b, base + Math.max(Math.min(high, heightAt(to)), low)],
                            [...a, base + Math.max(Math.min(high, heightAt(from)), low)],
                        ],
                        colour: OPENING_COLOURS[opening.kind] || OPENING_COLOURS.door,
                    });
                }
                faces.push(face);
            });
            for (const piece of ceiling.slopes.length ? ceiling.pieces() : []) {
                if (piece.source === null) {
                    continue;
                }
                faces.push({
                    kind: "slope",
                    points: piece.points.map(([x, y]) => [x, y, base + ceiling.at([x, y])[0]]),
                    colour: colours[`${room.id}:slope:${piece.source}`] || "#ffffff",
                });
            }
        }
    }
    return faces;
}

/** The middle and the size of the scene. */
export function sceneBounds(faces) {
    const xs = [];
    const ys = [];
    const zs = [];
    for (const face of faces) {
        for (const [x, y, z] of face.points) {
            xs.push(x);
            ys.push(y);
            zs.push(z);
        }
    }
    if (!xs.length) {
        return { centre: [0, 0, 0], radius: 1 };
    }
    const middle = (values) => (Math.min(...values) + Math.max(...values)) / 2;
    const span = (values) => Math.max(...values) - Math.min(...values);
    return {
        centre: [middle(xs), middle(ys), middle(zs)],
        radius: Math.max(Math.hypot(span(xs), span(ys), span(zs)) / 2, 1),
    };
}
