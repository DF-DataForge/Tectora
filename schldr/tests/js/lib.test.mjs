// Run with:  node --import ./tests/js/register.mjs --test tests/js/lib.test.mjs
//
// The editor measures a plan with its own copy of the library. These tests
// hold it to the fixtures the Python library wrote (tests/make_fixtures.py):
// the same document has to give the same surfaces, to the cent of a m².
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

const lib = new URL("../../schldr_paint/static/src/plan_editor/lib/", import.meta.url);
const documentLib = await import(new URL("document.js", lib));
const measure = await import(new URL("measure.js", lib));
const packs = await import(new URL("packs.js", lib));
const { History } = await import(new URL("history.js", lib));

const fixtures = new URL("../fixtures/", import.meta.url);

for (const name of readdirSync(fixtures).filter((file) => file.endsWith(".json"))) {
    const fixture = JSON.parse(readFileSync(new URL(name, fixtures), "utf-8"));
    test(`fixture ${name}: the document loads the same`, () => {
        assert.deepEqual(documentLib.load(fixture.document), fixture.expected.loaded);
    });
    test(`fixture ${name}: the same surfaces, rooms and assignments`, () => {
        const doc = documentLib.load(fixture.document);
        const result = measure.measureDocument(doc, fixture.options.deduct_min_area);
        assert.deepEqual(result.surfaces, fixture.expected.surfaces);
        assert.deepEqual(result.rooms, fixture.expected.rooms);
        assert.deepEqual(measure.assignments(doc, result.surfaces), fixture.expected.assignments);
    });
    test(`fixture ${name}: the same paint`, () => {
        const doc = documentLib.load(fixture.document);
        const { surfaces } = measure.measureDocument(doc, fixture.options.deduct_min_area);
        const needs = measure.materialNeeds(
            surfaces, measure.assignments(doc, surfaces), fixture.systems
        );
        const rounded = {};
        for (const [key, value] of needs) {
            rounded[key] = Math.round(value.quantity * 1e6) / 1e6;
        }
        assert.deepEqual(rounded, fixture.expected.needs);
    });
}

test("a loaded document survives a round trip", () => {
    const doc = documentLib.load({ levels: [{ rooms: [{ points: [[0, 0], [1000, 0], [1000, 1000]] }] }] });
    assert.deepEqual(documentLib.load(documentLib.dump(doc)), doc);
    assert.equal(new Set(doc.levels[0].rooms[0].walls.map((wall) => wall.id)).size, 3);
});

test("pots", () => {
    const sizes = [1, 2.5, 5, 10];
    assert.deepEqual(packs.choosePacks(0, sizes), []);
    assert.deepEqual(packs.choosePacks(4, sizes), [[5, 1]]);
    assert.deepEqual(packs.choosePacks(6, sizes), [[5, 1], [1, 1]]);
    assert.deepEqual(packs.choosePacks(9, sizes), [[10, 1]]);
    assert.deepEqual(packs.choosePacks(23, sizes), [[10, 2], [2.5, 1], [1, 1]]);
    assert.deepEqual(packs.choosePacks(3.2, [[1, 20], [2.5, 45], [5, 60]]), [[5, 1]]);
    assert.equal(packs.describe([[10, 2], [2.5, 1]]), "2 x 10 L + 1 x 2,5 L");
    for (let tenths = 1; tenths < 400; tenths++) {
        const need = tenths / 10;
        assert.ok(packs.packedVolume(packs.choosePacks(need, [0.75, 2.5, 10])) >= need - 1e-9);
    }
});

test("undo and redo", () => {
    const history = new History();
    history.push("a");
    history.push("b");
    assert.equal(history.undo("c"), "b");
    assert.equal(history.undo("b"), "a");
    assert.equal(history.undo("a"), null);
    assert.equal(history.redo("a"), "b");
    history.push("b");
    assert.equal(history.canRedo, false);
});

// ---- editing ----------------------------------------------------------------
const edit = await import(new URL("edit.js", lib));

function plan() {
    const doc = documentLib.emptyDocument();
    const level = doc.levels[0];
    const room = edit.addRoom(doc, level, edit.rectanglePoints([0, 0], [5000, 4000]));
    return { doc, level, room };
}

test("a new room has a wall per side and the default height", () => {
    const { doc, room } = plan();
    assert.equal(room.walls.length, 4);
    assert.equal(room.height, 2600);
    assert.equal(room.name, "Ruimte 1");
    assert.deepEqual(documentLib.load(documentLib.dump(doc)), doc, "what the editor makes is a clean document");
});

test("stretching a wall keeps a rectangle a rectangle", () => {
    const { room } = plan();
    edit.stretchWall(room, 0, 6200);
    assert.deepEqual(room.points, [[0, 0], [6200, 0], [6200, 4000], [0, 4000]]);
    edit.stretchWall(room, 1, 3000);
    assert.deepEqual(room.points, [[0, 0], [6200, 0], [6200, 3000], [0, 3000]]);
});

test("a corner in a wall: paint, slope and openings follow", () => {
    const { doc, level, room } = plan();
    const wall = room.walls[0];
    edit.setAssign(room, `${room.id}:wall:${wall.id}`, [{ system: 4, colour: 2 }]);
    const door = edit.addOpening(doc, room, wall.id, { kind: "door" }, 4000);
    edit.toggleSlope(doc, room, wall.id);
    const added = edit.splitWall(doc, room, 0, 3000);
    assert.equal(room.points.length, 5);
    assert.deepEqual(room.points[1], [3000, 0]);
    assert.equal(door.wall, added.id);
    assert.equal(door.offset, 4000 - 465 - 3000);
    assert.deepEqual(room.assign[`${room.id}:wall:${added.id}`], [{ system: 4, colour: 2 }]);
    assert.equal(room.slopes.length, 2);
    const before = measure.measureRoom(level, room).find((s) => s.ref === `${room.id}:ceiling`);
    assert.ok(before.area_net < 20, "the slope still lowers the ceiling over the whole side");
    assert.ok(edit.removeCorner(room, 1));
    assert.equal(room.openings.length, 0);
    assert.equal(room.slopes.length, 1);
});

test("an opening stays on its wall", () => {
    const { doc, room } = plan();
    const window = edit.addOpening(doc, room, room.walls[1].id, { kind: "window", width: 1800 }, 100);
    assert.equal(window.offset, 0);
    edit.stretchWall(room, 1, 1500);
    assert.equal(window.width, 1500);
    assert.equal(window.offset, 0);
});

test("a copied room is a room of its own", () => {
    const { doc, level, room } = plan();
    const door = edit.addOpening(doc, room, room.walls[0].id, { kind: "door" }, 1000);
    edit.setAssign(room, `${door.id}:leaf`, []);
    const copy = edit.duplicateRoom(doc, level, room);
    assert.notEqual(copy.id, room.id);
    assert.equal(copy.openings[0].wall, copy.walls[0].id);
    assert.deepEqual(Object.keys(copy.assign), [`${copy.openings[0].id}:leaf`]);
    const ids = [...level.rooms.flatMap((r) => [r.id, ...r.walls.map((w) => w.id), ...r.openings.map((o) => o.id)])];
    assert.equal(new Set(ids).size, ids.length);
    assert.deepEqual(documentLib.load(documentLib.dump(doc)), doc);
});

test("levels", () => {
    const { doc, level } = plan();
    const upper = edit.copyLevel(doc, level);
    assert.equal(upper.elevation, 2900);
    assert.equal(upper.rooms.length, 1);
    assert.equal(upper.rooms[0].name, "Ruimte 1");
    edit.removeLevel(doc, upper.id);
    edit.removeLevel(doc, level.id);
    assert.equal(doc.levels.length, 1, "the last level stays");
});

test("snapping", () => {
    const { level } = plan();
    assert.deepEqual(edit.snapPoint(level, [5030, 3980], 60, 50), [5000, 4000], "onto a corner");
    assert.deepEqual(edit.snapPoint(level, [5030, 6020], 60, 50), [5000, 6000], "in line with a corner");
    assert.deepEqual(edit.snapPoint(level, [7030, 6020], 60, 50), [7050, 6000], "onto the grid");
    assert.deepEqual(edit.orthoPoint([0, 0], [3010, 140], 50), [3000, 0]);
    assert.deepEqual(edit.orthoPoint([0, 0], [2000, 2100], 50).map((v) => Math.round(v / 10)), [205, 205]);
});

// ---- 3D ---------------------------------------------------------------------
const scene3d = await import(new URL("scene3d.js", lib));

test("the scene has a floor, the walls and the sloped ceilings of a level", () => {
    const fixture = JSON.parse(readFileSync(new URL("house.json", fixtures), "utf-8"));
    const doc = documentLib.load(fixture.document);
    const attic = scene3d.buildScene(doc, ["L2"], { "R3:wall:W11": "#ff0000" });
    const count = (kind) => attic.filter((face) => face.kind === kind).length;
    assert.equal(count("floor"), 2);
    assert.equal(count("wall"), 10);
    assert.ok(count("slope") >= 4);
    const knee = attic.find((face) => face.colour === "#ff0000");
    assert.deepEqual(knee.points.map((point) => Math.round(point[2] * 100) / 100), [0, 0, 1, 1]);
    // the side wall follows the slopes: 1.0 up to 2.4, flat, down to 0.8
    const side = attic.filter((face) => face.kind === "wall")[1];
    const heights = side.points.slice(2).map((point) => Math.round(point[2] * 100) / 100);
    assert.deepEqual([...new Set(heights)], [0.8, 2.4, 1]);
    assert.equal(side.decals.length, 1);
    const { radius } = scene3d.sceneBounds(scene3d.buildScene(doc, null));
    assert.ok(radius > 4);
});
