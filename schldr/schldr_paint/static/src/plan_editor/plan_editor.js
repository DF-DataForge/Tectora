/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, useProps } from "@odoo/owl";

import * as geometry from "./lib/geometry";
import * as planDocument from "./lib/document";
import * as measure from "./lib/measure";
import * as edit from "./lib/edit";
import { choosePacks, describe, packedVolume } from "./lib/packs";
import { History } from "./lib/history";
import { drawPlan, fitView, formatMetres, hitTest, toWorld, wallLength } from "./plan_view";
import { Plan3DDialog } from "./plan_3d";

const GROUP_LABELS = {
    walls: "Muren",
    ceilings: "Plafonds",
    floors: "Vloeren",
    woodwork: "Houtwerk",
    objects: "Objecten",
};
const UNITS = { m2: "m²", m: "m", piece: "st" };
const TOOL_KEYS = { v: "select", r: "rect", p: "polygon", d: "door", w: "window", i: "item", s: "slope", b: "brush" };
const STATUS = {
    select: "Klik een ruimte, muur of opening. Sleep een ruimte of een hoek; dubbelklik op een muur voor een extra hoek.",
    rect: "Sleep een rechthoek, of vul breedte en diepte in en klik waar de ruimte moet komen.",
    polygon: "Klik de hoeken. Wijs een richting aan en typ een lengte (m) + Enter. Enter of klik op het eerste punt sluit de ruimte.",
    door: "Klik op een muur om de deur te plaatsen.",
    window: "Klik op een muur om het raam te plaatsen.",
    item: "Klik op een muur om de radiator te plaatsen.",
    slope: "Klik op de muur waar het schuine plafond begint (nog eens klikken haalt het weg).",
    brush: "Klik een muur voor die muur, of in een ruimte voor alles van die soort. Alt-klik neemt over wat er staat.",
    pan: "Sleep om het plan te verschuiven.",
};

function parseMetres(text) {
    const value = parseFloat(String(text).replace(",", "."));
    return Number.isFinite(value) ? Math.round(value * 1000) : NaN;
}

function money(value, currency) {
    const text = value.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (!currency) {
        return text;
    }
    return currency.position === "before" ? `${currency.symbol} ${text}` : `${text} ${currency.symbol}`;
}

export class PlanEditorField extends Component {
    static template = "schldr_paint.PlanEditorField";
    props = useProps(standardFieldProps);

    setup() {
        this.canvasRef = signal.ref();
        this.wrapperRef = signal.ref();
        this.mainRef = signal.ref();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({
            tool: "select",
            levelId: null,
            selection: {}, // {room, wall, opening, item, corner}
            fullscreen: false,
            showGrid: true,
            snapStep: 50,
            panel: "room", // room | defaults | quote
            status: STATUS.select,
            typed: "", // the length being typed while drawing a polygon
            rectWidth: "",
            rectDepth: "",
            doorType: 0,
            windowType: 0,
            itemType: 0,
            brushSystem: 0, // 0: none chosen, -1: follow the defaults, -2: not painted
            brushColour: 0,
            options: { systems: [], colours: [], element_types: [], deduct_min_area: 0, products: {} },
            rev: 0, // goes up with every change of the document
        });
        this.history = new History();
        this.view = { zoom: 0.08, x: -1500, y: -1500 };
        this.drag = null;
        this.draft = null;
        this.hover = null;
        this._raw = undefined;
        this._staleRaw = null;
        this._doc = planDocument.emptyDocument();
        this._measured = null;
        this._destroyed = false;
        this._fitted = false;

        this.onWindowResize = () => this.resizeCanvas();
        onWillStart(async () => {
            try {
                this.state.options = await this.orm.call("schldr.project", "schldr_get_plan_options", []);
            } catch (error) {
                console.warn("Schldr: the plan options could not be loaded", error);
            }
            const types = this.state.options.element_types;
            const first = (kind) => (types.find((type) => type.kind === kind) || {}).id || 0;
            this.state.doorType = first("door");
            this.state.windowType = first("window");
            this.state.itemType = first("radiator");
        });
        onMounted(() => {
            this.resizeCanvas();
            window.addEventListener("resize", this.onWindowResize);
            if (window.ResizeObserver && this.mainRef()) {
                this._resizeObserver = new ResizeObserver(() => !this._destroyed && this.resizeCanvas());
                this._resizeObserver.observe(this.mainRef());
            }
        });
        onWillUnmount(() => {
            this._destroyed = true;
            clearTimeout(this._autoSyncTimer);
            if (this._resizeObserver) {
                this._resizeObserver.disconnect();
            }
            window.removeEventListener("resize", this.onWindowResize);
            document.body.classList.remove("o_schldr_plan_open");
        });
    }

    // ------------------------------------------------------------ document
    get readonly() {
        return Boolean(this.props.readonly);
    }

    /** The plan document of the record; re-read when the record changed
     *  under us (another tab, a reload), not when we wrote it ourselves. */
    get doc() {
        const raw = this.props.record.data[this.props.name] || "";
        if (raw === this._raw) {
            this._staleRaw = null;
        } else if (raw !== this._staleRaw) {
            this._raw = raw;
            this._measured = null;
            try {
                this._doc = planDocument.load(raw);
            } catch {
                this._doc = planDocument.emptyDocument();
            }
        }
        return this._doc;
    }

    get level() {
        const doc = this.doc;
        return doc.levels.find((level) => level.id === this.state.levelId) || doc.levels[0];
    }

    /** Write the document (changed in place) to the record. */
    commit() {
        this.history.push(this._raw || "");
        this.store(planDocument.dump(this._doc));
    }

    store(raw) {
        this._staleRaw = this.props.record.data[this.props.name] || "";
        this._raw = raw;
        this._measured = null;
        this.props.record.update({ [this.props.name]: raw });
        this.state.rev++;
        this.draw();
        this.scheduleAutoSync();
    }

    undo() {
        const raw = this.history.undo(this._raw || "");
        if (raw !== null) {
            this.restore(raw);
        }
    }

    redo() {
        const raw = this.history.redo(this._raw || "");
        if (raw !== null) {
            this.restore(raw);
        }
    }

    restore(raw) {
        try {
            this._doc = planDocument.load(raw);
        } catch {
            return;
        }
        this.state.selection = {};
        this.draft = null;
        this.store(raw);
    }

    scheduleAutoSync() {
        clearTimeout(this._autoSyncTimer);
        this._autoSyncTimer = setTimeout(() => this.autoSync(), 900);
    }

    /** Save and let the server rebuild rooms, surfaces and the quotation
     *  that follows the plan. Only for a project that was saved before. */
    async autoSync() {
        const record = this.props.record;
        if (this._destroyed || !record.resId || this.drag) {
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
            await this.orm.call("schldr.project", "action_sync_from_canvas", [record.resId]);
            await record.load();
            this.draw();
        } catch (error) {
            console.warn("Schldr: syncing the plan failed", error);
        } finally {
            this._syncing = false;
            if (this._syncPending) {
                this._syncPending = false;
                this.autoSync();
            }
        }
    }

    // --------------------------------------------------------------- derived
    /** Everything measured in the document, worked out once per change. */
    get measured() {
        const doc = this.doc;
        if (!this._measured) {
            const result = measure.measureDocument(doc, this.state.options.deduct_min_area || 0);
            const assigned = measure.assignments(doc, result.surfaces);
            const byRoom = {};
            for (const surface of result.surfaces) {
                (byRoom[surface.room] = byRoom[surface.room] || []).push(surface);
            }
            const roomAreas = {};
            for (const room of result.rooms) {
                roomAreas[room.ref] = room.floor_area;
            }
            this._measured = { ...result, assigned, byRoom, roomAreas };
        }
        return this._measured;
    }

    get systems() {
        return this.state.options.systems;
    }

    system(id) {
        return this.systems.find((system) => system.id === id);
    }

    colour(id) {
        return this.state.options.colours.find((colour) => colour.id === id);
    }

    systemsFor(group) {
        return this.systems.filter((system) => system.groups.includes(group));
    }

    presets(kind) {
        return this.state.options.element_types.filter((type) => type.kind === kind);
    }

    groupLabel(group) {
        return GROUP_LABELS[group] || group;
    }

    get groups() {
        return planDocument.GROUPS;
    }

    get selectedRoom() {
        this.state.rev;
        const id = this.state.selection.room;
        return id ? this.level.rooms.find((room) => room.id === id) || null : null;
    }

    get selectedWall() {
        const room = this.selectedRoom;
        const id = this.state.selection.wall;
        if (!room || !id) {
            return null;
        }
        const index = room.walls.findIndex((wall) => wall.id === id);
        if (index < 0) {
            return null;
        }
        return {
            wall: room.walls[index],
            index,
            length: formatMetres(wallLength(room, index)),
            slope: room.slopes.find((slope) => slope.wall === id) || null,
            openings: room.openings.filter((opening) => opening.wall === id),
        };
    }

    get selectedOpening() {
        const room = this.selectedRoom;
        const id = this.state.selection.opening;
        return room && id ? room.openings.find((opening) => opening.id === id) || null : null;
    }

    get selectedItem() {
        const room = this.selectedRoom;
        const id = this.state.selection.item;
        return room && id ? room.items.find((item) => item.id === id) || null : null;
    }

    /** The surfaces of a room as rows of the side panel. */
    surfaceRows(room) {
        this.state.rev;
        const measured = this.measured;
        return (measured.byRoom[room.id] || []).map((surface) => {
            const explicit = room.assign[surface.ref];
            const effective = (measured.assigned[surface.ref] || [])[0] || null;
            const system = effective ? this.system(effective.system) : null;
            const unit = system ? UNITS[system.measure] : surface.length && !surface.area_net ? "m" : "m²";
            const size = system
                ? measure.quantity(surface, system.measure)
                : surface.area_net || surface.length || surface.count;
            return {
                surface,
                size: `${size.toFixed(2).replace(".", ",")} ${unit}`,
                mode: explicit === undefined ? "default" : explicit.length ? "own" : "none",
                system: effective ? effective.system : 0,
                colour: effective ? effective.colour || 0 : 0,
                swatch: effective && effective.colour ? (this.colour(effective.colour) || {}).hex : "",
                options: this.systemsFor(surface.group),
            };
        });
    }

    defaultEntry(group) {
        this.state.rev;
        return (this.doc.defaults.assign[group] || [])[0] || { system: 0, colour: 0 };
    }

    /** The quotation as the plan builds it: per room a line per group,
     *  system and colour, at catalogue prices. */
    get quote() {
        this.state.rev;
        const measured = this.measured;
        const currency = this.state.options.currency;
        const sections = [];
        let total = 0;
        let hours = 0;
        for (const [level, room] of planDocument.iterRooms(this.doc)) {
            const lines = new Map();
            for (const surface of measured.byRoom[room.id] || []) {
                for (const entry of measured.assigned[surface.ref] || []) {
                    const system = this.system(entry.system);
                    if (!system) {
                        continue;
                    }
                    const key = `${surface.group}|${entry.system}|${entry.colour || 0}`;
                    const line = lines.get(key) || {
                        key, group: surface.group, system, colour: this.colour(entry.colour), quantity: 0,
                    };
                    line.quantity += measure.quantity(surface, system.measure);
                    lines.set(key, line);
                }
            }
            if (!lines.size) {
                continue;
            }
            const rows = [...lines.values()]
                .sort((a, b) => this.groups.indexOf(a.group) - this.groups.indexOf(b.group))
                .map((line) => {
                    const amount = line.quantity * line.system.price;
                    total += amount;
                    hours += line.quantity * line.system.hours;
                    return {
                        key: line.key,
                        label: `${GROUP_LABELS[line.group]} – ${line.system.name}`,
                        colour: line.colour ? line.colour.name : "",
                        swatch: line.colour ? line.colour.hex : "",
                        quantity: `${line.quantity.toFixed(2).replace(".", ",")} ${UNITS[line.system.measure]}`,
                        amount: money(amount, currency),
                    };
                });
            const title = this.doc.levels.length > 1 ? `${level.name} – ${room.name}` : room.name;
            sections.push({ id: room.id, title, rows });
        }
        return { sections, total: money(total, currency), hours: hours.toFixed(1).replace(".", ",") };
    }

    /** The paint the plan takes, per product and colour, in pots. */
    get paint() {
        this.state.rev;
        const measured = this.measured;
        const recipe = {};
        for (const system of this.systems) {
            recipe[system.id] = { layers: system.layers };
        }
        const needs = measure.materialNeeds(measured.surfaces, measured.assigned, recipe);
        const products = this.state.options.products || {};
        return [...needs.values()]
            .filter((need) => need.quantity > 1e-6)
            .map((need) => {
                const product = products[need.product] || { name: `#${need.product}`, uom: "", packs: [] };
                const chosen = choosePacks(need.quantity, product.packs);
                const colour = need.colour ? this.colour(need.colour) : null;
                return {
                    key: `${need.product}|${need.colour || 0}`,
                    name: product.name,
                    colour: colour ? colour.name : "",
                    swatch: colour ? colour.hex : "",
                    need: `${need.quantity.toFixed(2).replace(".", ",")} ${product.uom}`,
                    packs: chosen.length
                        ? `${describe(chosen, product.uom)} (${String(packedVolume(chosen)).replace(".", ",")} ${product.uom})`
                        : "",
                };
            })
            .sort((a, b) => a.name.localeCompare(b.name) || a.colour.localeCompare(b.colour));
    }

    // ---------------------------------------------------------------- canvas
    resizeCanvas() {
        const canvas = this.canvasRef();
        const main = this.mainRef();
        if (!canvas || !main) {
            return;
        }
        const width = Math.max(main.clientWidth, 300);
        const height = this.state.fullscreen
            ? Math.max(window.innerHeight - main.getBoundingClientRect().top - 34, 300)
            : 560;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        this.size = { width, height, ratio };
        if (!this._fitted) {
            this._fitted = true;
            this.view = fitView(this.level, width, height);
        }
        this.draw();
    }

    draw() {
        const canvas = this.canvasRef();
        if (!canvas || !this.size) {
            return;
        }
        const ctx = canvas.getContext("2d");
        const { width, height, ratio } = this.size;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        const measured = this.measured;
        drawPlan(ctx, this.view, width, height, {
            level: this.level,
            selection: this.state.selection,
            hover: this.hover,
            showGrid: this.state.showGrid,
            showSizes: true,
            roomAreas: measured.roomAreas,
            roomTint: () => null,
            wallColour: (room, wall) => {
                const entry = (measured.assigned[`${room.id}:wall:${wall.id}`] || [])[0];
                const colour = entry && entry.colour ? this.colour(entry.colour) : null;
                return colour ? colour.hex : entry ? "#c9d1da" : null;
            },
            draft: this.draft,
        });
    }

    fit() {
        if (this.size) {
            this.view = fitView(this.level, this.size.width, this.size.height);
            this.draw();
        }
    }

    zoomBy(factor, centre = null) {
        if (!this.size) {
            return;
        }
        const point = centre || [this.size.width / 2, this.size.height / 2];
        const world = toWorld(this.view, point);
        const zoom = Math.min(Math.max(this.view.zoom * factor, 0.005), 2);
        this.view = { zoom, x: world[0] - point[0] / zoom, y: world[1] - point[1] / zoom };
        this.draw();
    }

    onWheel(ev) {
        ev.preventDefault();
        this.zoomBy(ev.deltaY < 0 ? 1.15 : 1 / 1.15, this.canvasPoint(ev));
    }

    canvasPoint(ev) {
        const rect = this.canvasRef().getBoundingClientRect();
        return [ev.clientX - rect.left, ev.clientY - rect.top];
    }

    worldPoint(ev) {
        return toWorld(this.view, this.canvasPoint(ev));
    }

    get tolerance() {
        return 9 / this.view.zoom;
    }

    // ------------------------------------------------------------------ tools
    /** A choice in the toolbar (a select gives text, the state wants a number). */
    pickNumber(key, value) {
        this.state[key] = parseInt(value, 10) || 0;
    }

    setTool(tool) {
        if (this.readonly && tool !== "pan" && tool !== "select") {
            return;
        }
        this.state.tool = tool;
        this.state.status = STATUS[tool] || "";
        this.state.typed = "";
        this.draft = null;
        this.drag = null;
        if (tool === "brush") {
            this.state.panel = "room";
        }
        this.draw();
    }

    toggleFullscreen() {
        this.state.fullscreen = !this.state.fullscreen;
        document.body.classList.toggle("o_schldr_plan_open", this.state.fullscreen);
        // the canvas gets its new size once the class is on
        setTimeout(() => {
            this.resizeCanvas();
            this.fit();
        });
    }

    select(selection) {
        this.state.selection = selection;
        if (selection.room) {
            this.state.panel = "room";
        }
        this.draw();
    }

    onPointerDown(ev) {
        const canvas = this.canvasRef();
        canvas.focus();
        const screen = this.canvasPoint(ev);
        const world = toWorld(this.view, screen);
        const tool = this.state.tool;
        if (ev.button === 1 || ev.button === 2 || tool === "pan") {
            this.drag = { mode: "pan", screen, view: { ...this.view } };
            canvas.setPointerCapture(ev.pointerId);
            return;
        }
        if (ev.button !== 0) {
            return;
        }
        const hit = this.hitAt(world);
        if (tool === "select") {
            if (!hit) {
                this.select({});
                this.drag = { mode: "pan", screen, view: { ...this.view } };
                canvas.setPointerCapture(ev.pointerId);
                return;
            }
            if (hit.corner !== undefined) {
                this.select({ room: hit.room, corner: hit.corner });
                this.drag = { mode: "corner", room: hit.room, index: hit.corner, moved: false };
            } else if (hit.opening) {
                this.select({ room: hit.room, wall: hit.wall, opening: hit.opening });
                this.drag = { mode: "opening", room: hit.room, id: hit.opening, grab: hit.offset, moved: false };
            } else if (hit.item) {
                this.select({ room: hit.room, wall: hit.wall, item: hit.item });
                this.drag = { mode: "item", room: hit.room, id: hit.item, grab: hit.offset, moved: false };
            } else if (hit.wall) {
                this.select({ room: hit.room, wall: hit.wall });
            } else {
                const room = this.level.rooms.find((candidate) => candidate.id === hit.room);
                const wasSelected = this.state.selection.room === hit.room;
                this.select({ room: hit.room });
                // a room is selected first, then dragged
                if (wasSelected && room) {
                    this.drag = {
                        mode: "room", room: hit.room, start: world,
                        points: room.points.map((point) => [...point]), moved: false,
                    };
                }
            }
            if (this.drag && !this.readonly) {
                canvas.setPointerCapture(ev.pointerId);
            } else {
                this.drag = null;
            }
            return;
        }
        if (this.readonly) {
            return;
        }
        if (tool === "rect") {
            const start = edit.snapPoint(this.level, world, this.tolerance, this.state.snapStep);
            const width = parseMetres(this.state.rectWidth);
            const depth = parseMetres(this.state.rectDepth);
            if (width > 0 && depth > 0) {
                this.createRoom(edit.rectanglePoints(start, [start[0] + width, start[1] + depth]));
                return;
            }
            this.drag = { mode: "rect", start };
            this.draft = { kind: "rect", points: edit.rectanglePoints(start, start) };
            canvas.setPointerCapture(ev.pointerId);
        } else if (tool === "polygon") {
            this.polygonClick(world, ev);
        } else if (tool === "door" || tool === "window" || tool === "item") {
            this.placeOnWall(tool, hit);
        } else if (tool === "slope") {
            if (hit && hit.wall) {
                const room = this.level.rooms.find((candidate) => candidate.id === hit.room);
                edit.toggleSlope(this._doc, room, hit.wall);
                this.select({ room: hit.room, wall: hit.wall });
                this.commit();
            }
        } else if (tool === "brush") {
            if (ev.altKey) {
                this.pickBrush(hit);
            } else {
                this.paint_(hit);
            }
        }
    }

    hitAt(world) {
        return hitTest(this.level, world, this.tolerance, this.state.selection.room);
    }

    onPointerMove(ev) {
        const screen = this.canvasPoint(ev);
        const world = toWorld(this.view, screen);
        const drag = this.drag;
        if (drag && drag.mode === "pan") {
            this.view = {
                zoom: this.view.zoom,
                x: drag.view.x - (screen[0] - drag.screen[0]) / this.view.zoom,
                y: drag.view.y - (screen[1] - drag.screen[1]) / this.view.zoom,
            };
            this.draw();
            return;
        }
        if (drag) {
            const room = drag.room && this.level.rooms.find((candidate) => candidate.id === drag.room);
            if (drag.mode === "rect") {
                const end = edit.snapPoint(this.level, world, this.tolerance, this.state.snapStep);
                this.draft = { kind: "rect", points: edit.rectanglePoints(drag.start, end) };
            } else if (drag.mode === "corner" && room) {
                const point = edit.snapPoint(this.level, world, this.tolerance, this.state.snapStep, drag.room);
                edit.moveCorner(room, drag.index, this.alignCorner(room, drag.index, point, ev.shiftKey));
                drag.moved = true;
                this._measured = null;
            } else if (drag.mode === "room" && room) {
                const dx = edit.snap(world[0] - drag.start[0], this.state.snapStep);
                const dy = edit.snap(world[1] - drag.start[1], this.state.snapStep);
                room.points = drag.points.map(([x, y]) => [x + dx, y + dy]);
                drag.moved = drag.moved || dx !== 0 || dy !== 0;
            } else if ((drag.mode === "opening" || drag.mode === "item") && room) {
                const part = (drag.mode === "opening" ? room.openings : room.items).find((p) => p.id === drag.id);
                const index = part ? room.walls.findIndex((wall) => wall.id === part.wall) : -1;
                if (index >= 0) {
                    const start = room.points[index];
                    const end = room.points[(index + 1) % room.points.length];
                    const near = geometry.nearestOnSegment(world, start, end);
                    const length = geometry.distance(start, end);
                    if (drag.delta === undefined) {
                        drag.delta = drag.grab - part.offset;
                    }
                    const offset = edit.snap(near.ratio * length - drag.delta, 10);
                    part.offset = Math.max(Math.min(offset, Math.round(length) - part.width), 0);
                    drag.moved = true;
                    this._measured = null;
                }
            }
            this.draw();
            return;
        }
        if (this.state.tool === "polygon" && this.draft) {
            this.draft.cursor = this.polygonPoint(world, ev.shiftKey);
            this.draw();
            return;
        }
        // show which wall a click would take
        const hit = this.hitAt(world);
        const hover = hit && hit.wall ? { room: hit.room, wall: hit.wall } : null;
        if (JSON.stringify(hover) !== JSON.stringify(this.hover)) {
            this.hover = hover;
            this.draw();
        }
    }

    /** A dragged corner keeps its two walls straight when it is close to
     *  being in line with its neighbours (Shift lets it go free). */
    alignCorner(room, index, point, free) {
        if (free) {
            return point;
        }
        const count = room.points.length;
        const result = [...point];
        for (const neighbour of [room.points[(index - 1 + count) % count], room.points[(index + 1) % count]]) {
            if (Math.abs(neighbour[0] - result[0]) <= this.tolerance) {
                result[0] = neighbour[0];
            }
            if (Math.abs(neighbour[1] - result[1]) <= this.tolerance) {
                result[1] = neighbour[1];
            }
        }
        return result;
    }

    onPointerUp(ev) {
        const drag = this.drag;
        this.drag = null;
        const canvas = this.canvasRef();
        if (canvas && canvas.hasPointerCapture && canvas.hasPointerCapture(ev.pointerId)) {
            canvas.releasePointerCapture(ev.pointerId);
        }
        if (!drag) {
            return;
        }
        if (drag.mode === "rect") {
            const points = this.draft ? this.draft.points : [];
            this.draft = null;
            if (points.length === 4 && geometry.area(points) > 250000) {
                this.createRoom(points);
            } else {
                this.draw();
            }
        } else if (drag.moved) {
            const room = this.level.rooms.find((candidate) => candidate.id === drag.room);
            if (room) {
                edit.clampOpenings(room);
            }
            this.commit();
        }
    }

    onDoubleClick(ev) {
        if (this.readonly || this.state.tool !== "select") {
            return;
        }
        const hit = this.hitAt(this.worldPoint(ev));
        if (hit && hit.wall && !hit.opening && !hit.item) {
            const room = this.level.rooms.find((candidate) => candidate.id === hit.room);
            const added = edit.splitWall(this._doc, room, hit.wallIndex, edit.snap(hit.offset, this.state.snapStep));
            if (added) {
                this.select({ room: room.id, corner: hit.wallIndex + 1 });
                this.commit();
            }
        }
    }

    createRoom(points) {
        const room = edit.addRoom(this._doc, this.level, points);
        this.select({ room: room.id });
        this.commit();
    }

    // -------------------------------------------------------------- polygon
    polygonPoint(world, free) {
        const points = this.draft ? this.draft.points : [];
        if (!points.length) {
            return edit.snapPoint(this.level, world, this.tolerance, this.state.snapStep);
        }
        if (points.length >= 3 && geometry.distance(world, points[0]) <= this.tolerance * 1.4) {
            return [...points[0]];
        }
        const origin = points[points.length - 1];
        const snapped = edit.snapPoint(this.level, world, this.tolerance, this.state.snapStep);
        // on a corner of another room: take it as it is
        if (snapped[0] !== edit.snap(world[0], this.state.snapStep) && snapped[1] !== edit.snap(world[1], this.state.snapStep)) {
            return snapped;
        }
        return edit.orthoPoint(origin, world, this.state.snapStep, free);
    }

    polygonClick(world, ev) {
        const point = this.polygonPoint(world, ev.shiftKey);
        if (!this.draft) {
            this.draft = { kind: "polygon", points: [point], cursor: point };
        } else if (this.draft.points.length >= 3 && geometry.distance(point, this.draft.points[0]) < 1) {
            this.closePolygon();
            return;
        } else {
            this.draft.points.push(point);
        }
        this.state.typed = "";
        this.draw();
    }

    closePolygon() {
        const points = this.draft ? this.draft.points : [];
        this.draft = null;
        this.state.typed = "";
        if (points.length >= 3 && geometry.area(points) > 250000) {
            this.createRoom(points);
        } else {
            this.draw();
        }
    }

    /** The side being drawn gets the typed length, in the direction the
     *  pointer shows. */
    applyTypedLength() {
        const length = parseMetres(this.state.typed);
        const draft = this.draft;
        if (!draft || !draft.cursor || !(length > 0)) {
            return false;
        }
        const origin = draft.points[draft.points.length - 1];
        const reach = geometry.distance(origin, draft.cursor);
        if (reach < 1) {
            return false;
        }
        draft.points.push([
            Math.round(origin[0] + ((draft.cursor[0] - origin[0]) / reach) * length),
            Math.round(origin[1] + ((draft.cursor[1] - origin[1]) / reach) * length),
        ]);
        this.state.typed = "";
        this.draw();
        return true;
    }

    // ---------------------------------------------------------------- places
    placeOnWall(tool, hit) {
        if (!hit || !hit.wall) {
            this.notification.add("Klik op een muur.", { type: "info" });
            return;
        }
        const room = this.level.rooms.find((candidate) => candidate.id === hit.room);
        const types = this.state.options.element_types;
        if (tool === "item") {
            const preset = types.find((type) => type.id === this.state.itemType) || { kind: "radiator" };
            const item = edit.addRadiator(this._doc, room, hit.wall, preset, hit.offset);
            this.select({ room: room.id, wall: hit.wall, item: item.id });
        } else {
            const id = tool === "door" ? this.state.doorType : this.state.windowType;
            const preset = types.find((type) => type.id === id) || { kind: tool };
            const opening = edit.addOpening(this._doc, room, hit.wall, preset, hit.offset);
            this.select({ room: room.id, wall: hit.wall, opening: opening.id });
        }
        this.commit();
    }

    // ----------------------------------------------------------------- brush
    brushEntries() {
        const system = this.state.brushSystem;
        if (system === -1) {
            return undefined; // follow the defaults
        }
        if (system === -2) {
            return []; // not painted
        }
        return [{ system, colour: this.state.brushColour || false }];
    }

    paint_(hit) {
        const system = this.system(this.state.brushSystem);
        if (!hit || (!system && this.state.brushSystem >= 0)) {
            if (hit) {
                this.notification.add("Kies eerst een verfsysteem voor de kwast.", { type: "info" });
            }
            return;
        }
        const room = this.level.rooms.find((candidate) => candidate.id === hit.room);
        const surfaces = this.measured.byRoom[room.id] || [];
        const fits = (surface) => !system || system.groups.includes(surface.group);
        let targets;
        if (hit.opening) {
            targets = surfaces.filter((s) => s.ref.startsWith(`${hit.opening}:`) && fits(s));
        } else if (hit.item) {
            targets = surfaces.filter((s) => s.ref === hit.item && fits(s));
        } else if (hit.wall && (!system || system.groups.includes("walls"))) {
            targets = surfaces.filter((s) => s.ref === `${room.id}:wall:${hit.wall}`);
        } else {
            // in the room: everything of the kind the system is for
            targets = surfaces.filter((s) => system ? fits(s) : s.group !== "walls");
        }
        if (!targets.length) {
            this.notification.add("Dit verfsysteem past niet op wat je aanklikt.", { type: "info" });
            return;
        }
        const entries = this.brushEntries();
        for (const surface of targets) {
            edit.setAssign(room, surface.ref, entries);
        }
        this.select({ room: room.id });
        this.commit();
    }

    pickBrush(hit) {
        if (!hit) {
            return;
        }
        const reference = hit.wall ? `${hit.room}:wall:${hit.wall}` : `${hit.room}:ceiling`;
        const entry = (this.measured.assigned[reference] || [])[0];
        if (entry) {
            this.state.brushSystem = entry.system;
            this.state.brushColour = entry.colour || 0;
        }
    }

    // ------------------------------------------------------------- keyboard
    onKeyDown(ev) {
        if (["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) {
            return;
        }
        const key = ev.key;
        if ((ev.ctrlKey || ev.metaKey) && key.toLowerCase() === "z") {
            ev.preventDefault();
            ev.shiftKey ? this.redo() : this.undo();
            return;
        }
        if ((ev.ctrlKey || ev.metaKey) && key.toLowerCase() === "y") {
            ev.preventDefault();
            this.redo();
            return;
        }
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            return;
        }
        if (this.state.tool === "polygon" && this.draft) {
            if (/^[0-9.,]$/.test(key)) {
                this.state.typed += key;
                ev.preventDefault();
                return;
            }
            if (key === "Backspace") {
                if (this.state.typed) {
                    this.state.typed = this.state.typed.slice(0, -1);
                } else {
                    this.draft.points.pop();
                    if (!this.draft.points.length) {
                        this.draft = null;
                    }
                    this.draw();
                }
                ev.preventDefault();
                return;
            }
            if (key === "Enter") {
                ev.preventDefault();
                if (!this.applyTypedLength()) {
                    this.closePolygon();
                }
                return;
            }
        }
        if (key === "Escape") {
            if (this.draft) {
                this.draft = null;
                this.state.typed = "";
                this.draw();
            } else if (this.state.tool !== "select") {
                this.setTool("select");
            } else if (this.state.fullscreen) {
                this.toggleFullscreen();
            }
            ev.preventDefault();
        } else if (key === "Delete" || key === "Backspace") {
            this.deleteSelected();
            ev.preventDefault();
        } else if (key.toLowerCase() === "f") {
            this.toggleFullscreen();
        } else if (TOOL_KEYS[key.toLowerCase()]) {
            this.setTool(TOOL_KEYS[key.toLowerCase()]);
        }
    }

    deleteSelected() {
        if (this.readonly) {
            return;
        }
        const selection = this.state.selection;
        const room = this.selectedRoom;
        if (!room) {
            return;
        }
        if (selection.opening) {
            room.openings = room.openings.filter((opening) => opening.id !== selection.opening);
            for (const key of Object.keys(room.assign)) {
                if (key.startsWith(`${selection.opening}:`)) {
                    delete room.assign[key];
                }
            }
            this.state.selection = { room: room.id, wall: selection.wall };
        } else if (selection.item) {
            room.items = room.items.filter((item) => item.id !== selection.item);
            delete room.assign[selection.item];
            this.state.selection = { room: room.id };
        } else if (selection.corner !== undefined) {
            if (!edit.removeCorner(room, selection.corner)) {
                return;
            }
            this.state.selection = { room: room.id };
        } else if (selection.wall) {
            return; // a wall goes by taking out one of its corners
        } else {
            edit.removeRoom(this._doc, room.id);
            this.state.selection = {};
        }
        this.commit();
    }

    // ------------------------------------------------------------ side panel
    change(mutate) {
        if (this.readonly) {
            return;
        }
        mutate();
        this.commit();
    }

    setRoomName(room, value) {
        this.change(() => {
            room.name = value.trim() || room.name;
        });
    }

    setRoomHeight(room, value) {
        const height = parseMetres(value);
        if (height > 0) {
            this.change(() => {
                room.height = height;
            });
        }
    }

    toggleHas(room, key) {
        this.change(() => {
            room.has[key] = !room.has[key];
        });
    }

    duplicateSelected() {
        const room = this.selectedRoom;
        if (room && !this.readonly) {
            const copy = edit.duplicateRoom(this._doc, this.level, room);
            this.state.selection = { room: copy.id };
            this.commit();
        }
    }

    setWallLength(room, index, value) {
        const length = parseMetres(value);
        if (length > 0) {
            this.change(() => edit.stretchWall(room, index, length));
        }
    }

    toggleVirtual(wall) {
        this.change(() => {
            wall.virtual = !wall.virtual;
        });
    }

    toggleOwnHeight(room, wall) {
        this.change(() => {
            wall.h = wall.h ? null : [room.height, room.height];
        });
    }

    setWallHeight(wall, end, value) {
        const height = parseMetres(value);
        if (height >= 0 && wall.h) {
            this.change(() => {
                wall.h[end] = height;
            });
        }
    }

    toggleSlope(room, wall) {
        this.change(() => edit.toggleSlope(this._doc, room, wall.id));
    }

    /** A number typed in the panel: metres for sizes, plain for the rest. */
    setNumber(part, key, value, metres = true) {
        const number = metres ? parseMetres(value) : parseFloat(String(value).replace(",", "."));
        if (Number.isFinite(number) && number >= 0) {
            this.change(() => {
                part[key] = number;
                const room = this.selectedRoom;
                if (room) {
                    edit.clampOpenings(room);
                }
            });
        }
    }

    setFlag(part, key) {
        this.change(() => {
            part[key] = !part[key];
        });
    }

    setText(part, key, value) {
        this.change(() => {
            part[key] = value;
        });
    }

    metres(mm) {
        return formatMetres(mm || 0);
    }

    addCustomItem() {
        const room = this.selectedRoom;
        if (room && !this.readonly) {
            const item = edit.addCustomItem(this._doc, room);
            this.state.selection = { room: room.id, item: item.id };
            this.commit();
        }
    }

    /** The select of a surface row: "default", "none" or a system id. */
    setSurfaceSystem(room, row, value) {
        this.change(() => {
            if (value === "default") {
                edit.setAssign(room, row.surface.ref, undefined);
            } else if (value === "none") {
                edit.setAssign(room, row.surface.ref, []);
            } else {
                edit.setAssign(room, row.surface.ref, [
                    { system: parseInt(value, 10), colour: row.colour || false },
                ]);
            }
        });
    }

    setSurfaceColour(room, row, value) {
        if (!row.system) {
            return;
        }
        this.change(() =>
            edit.setAssign(room, row.surface.ref, [
                { system: row.system, colour: parseInt(value, 10) || false },
            ])
        );
    }

    setDefault(group, key, value) {
        this.change(() => {
            const current = { ...this.defaultEntry(group) };
            current[key] = parseInt(value, 10) || 0;
            if (current.system) {
                this._doc.defaults.assign[group] = [
                    { system: current.system, colour: current.colour || false },
                ];
            } else {
                delete this._doc.defaults.assign[group];
            }
        });
    }

    setDefaultHeight(value) {
        const height = parseMetres(value);
        if (height > 0) {
            this.change(() => {
                this._doc.defaults.height = height;
            });
        }
    }

    // ---------------------------------------------------------------- levels
    openLevel(level) {
        this.state.levelId = level.id;
        this.state.selection = {};
        this.draft = null;
        this.fit();
    }

    addLevel(copy) {
        if (this.readonly) {
            return;
        }
        const level = copy ? edit.copyLevel(this._doc, this.level) : edit.addLevel(this._doc);
        this.state.levelId = level.id;
        this.state.selection = {};
        this.commit();
        this.fit();
    }

    renameLevel(value) {
        const level = this.level;
        this.change(() => {
            level.name = value.trim() || level.name;
        });
    }

    removeLevel() {
        if (this.readonly || this.doc.levels.length < 2) {
            return;
        }
        edit.removeLevel(this._doc, this.level.id);
        this.state.levelId = this._doc.levels[0].id;
        this.state.selection = {};
        this.commit();
        this.fit();
    }

    open3d() {
        const measured = this.measured;
        const colours = {};
        for (const [reference, entries] of Object.entries(measured.assigned)) {
            const colour = entries[0] && entries[0].colour ? this.colour(entries[0].colour) : null;
            colours[reference] = colour ? colour.hex : entries[0] ? "#e9edf1" : null;
        }
        this.dialog.add(Plan3DDialog, { document: this.doc, levelId: this.level.id, colours });
    }
}

export const planEditorField = {
    component: PlanEditorField,
    supportedTypes: ["text"],
    displayName: "Schldr plan editor",
};

registry.category("fields").add("schldr_plan", planEditorField);
