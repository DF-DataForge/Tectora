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
