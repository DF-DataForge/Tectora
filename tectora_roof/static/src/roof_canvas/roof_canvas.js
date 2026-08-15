/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { RoofProductPickerDialog } from "./product_picker_dialog";
import {
    Component,
    onMounted,
    onWillUnmount,
    useRef,
    useState,
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
// Default real-world size (meters) of roof objects added via right-click.
const OBJECT_DEFAULT_SIZE_M = { chimney: 0.8, skylight: 1.2 };
// Circles are stored as regular polygons so measurements and the server-side
// sync keep working; 48 points keeps area/perimeter within ~0.5% of exact.
const CIRCLE_POINTS = 48;

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
const KIND_NAMES = { section: "Sectie", chimney: "Schoorsteen", skylight: "Koepel" };

const KIND_STYLES = {
    section: { fill: "rgba(10, 116, 131, 0.28)", stroke: "#0a7483", label: "" },
    chimney: { fill: "rgba(217, 119, 6, 0.35)", stroke: "#b45309", label: "Schoorsteen" },
    skylight: { fill: "rgba(37, 99, 235, 0.30)", stroke: "#1d4ed8", label: "Koepel" },
};

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

export class RoofCanvasField extends Component {
    static template = "tectora_roof.RoofCanvasField";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = useRef("canvas");
        this.wrapperRef = useRef("wrapper");
        this.mainRef = useRef("main");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({
            tool: "select",
            showBackground: true,
            backgroundOpacity: 0.9,
            showGrid: true,
            gridStep: 1,
            selectedId: null,
            status: "",
            contextMenu: null, // {x, y (px in wrapper), worldPoint}
            panel: null, // product card for the selected shape
        });
        this.world = { ...DEFAULT_WORLD };
        this.view = { zoom: 1, x: 0, y: 0 };
        this.backgroundImage = null;
        this.drag = null; // {mode: 'move'|'rect'|'pan', ...}
        this.draftPolygon = null; // [[x, y], ...]
        this._rawCache = undefined;
        this._shapes = [];
        this.labelHits = []; // clickable measurement boxes, in world coordinates

        this.onWindowResize = () => this.resizeCanvas();

        onMounted(() => {
            this.resizeCanvas();
            this.loadBackground();
            window.addEventListener("resize", this.onWindowResize);
        });
        onWillUnmount(() => {
            window.removeEventListener("resize", this.onWindowResize);
        });
    }

    // ------------------------------------------------------------- record I/O
    get shapes() {
        const raw = this.props.record.data[this.props.name] || "";
        if (raw !== this._rawCache) {
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
        this._rawCache = raw;
        const values = { [this.props.name]: raw };
        const snapshot = this.exportSnapshot();
        if (snapshot && "canvas_snapshot" in this.props.record.data) {
            values.canvas_snapshot = snapshot;
        }
        this.props.record.update(values);
        this.draw();
        this.autoSyncFromCanvas();
    }

    async autoSyncFromCanvas() {
        // Keep the sections/objects in sync with the drawing without a manual
        // 'Meting bijwerken uit tekening' click. Only for already-saved
        // projects: on a brand-new record the drawing stays local until the
        // user saves it for the first time.
        const record = this.props.record;
        if (!record.resId) {
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
        const canvas = this.canvasRef.el;
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
        const canvas = this.canvasRef.el;
        const wrapper = this.mainRef.el || this.wrapperRef.el;
        if (!canvas || !wrapper) {
            return;
        }
        canvas.width = Math.max(wrapper.clientWidth - 2, 600);
        canvas.height = 620;
        this.fitView();
        this.draw();
    }

    loadBackground() {
        const url = this.backgroundUrl;
        if (!url) {
            this.world = { ...DEFAULT_WORLD };
            this.fitView();
            this.draw();
            return;
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
        const canvas = this.canvasRef.el;
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

    toWorld(ev) {
        const canvas = this.canvasRef.el;
        const rect = canvas.getBoundingClientRect();
        const cx = ((ev.clientX - rect.left) * canvas.width) / rect.width;
        const cy = ((ev.clientY - rect.top) * canvas.height) / rect.height;
        return [
            (cx - this.view.x) / this.view.zoom,
            (cy - this.view.y) / this.view.zoom,
        ];
    }

    // ------------------------------------------------------------- toolbar
    setTool(tool) {
        this.state.tool = tool;
        this.draftPolygon = null;
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

    zoomBy(factor) {
        const canvas = this.canvasRef.el;
        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        const newZoom = Math.min(Math.max(this.view.zoom * factor, 0.05), 20);
        this.view.x = cx - ((cx - this.view.x) / this.view.zoom) * newZoom;
        this.view.y = cy - ((cy - this.view.y) / this.view.zoom) * newZoom;
        this.view.zoom = newZoom;
        this.draw();
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
        if (this.state.tool === "rect") {
            this.drag = { mode: "rect", start: point, current: point };
        } else if (this.state.tool === "polygon") {
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
                    };
                    this.updateStatus();
                    this.draw();
                    this.refreshPanel();
                }
                return;
            }
            if (labelHit) {
                this.openProducts(labelHit);
                return;
            }
            const hit = this.hitTest(point);
            const wasSelected = hit && this.state.selectedId === hit.id;
            this.state.selectedId = hit ? hit.id : null;
            // Moving a whole shape requires selecting it first: the first
            // click only selects, dragging an already-selected shape moves.
            if (hit && wasSelected) {
                this.drag = {
                    mode: "move",
                    start: point,
                    original: hit.points.map((p) => [...p]),
                    shape: hit,
                    moved: false,
                };
            }
            this.updateStatus();
            this.draw();
            this.refreshPanel();
        }
    }

    onPointerMove(ev) {
        if (!this.drag) {
            if (this.state.tool === "select" && this.canvasRef.el) {
                const hover = this.labelHitTest(this.toWorld(ev));
                this.canvasRef.el.style.cursor = !hover
                    ? ""
                    : hover.type === "corner" || hover.type === "radius"
                    ? "move"
                    : "pointer";
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
        if (this.state.tool === "polygon" && this.draftPolygon) {
            this.closePolygon();
        } else if (this.state.tool === "select") {
            const hit = this.hitTest(this.toWorld(ev));
            if (hit) {
                this.state.selectedId = hit.id;
                this.renameSelected();
            }
        }
    }

    onKeyDown(ev) {
        if (ev.key === "Delete" || ev.key === "Backspace") {
            if (ev.target.tagName !== "INPUT") {
                ev.preventDefault();
                this.deleteSelected();
            }
        } else if (ev.key === "Escape") {
            this.draftPolygon = null;
            this.state.contextMenu = null;
            this.updateStatus();
            this.draw();
        } else if (ev.key === "Enter" && this.draftPolygon) {
            ev.preventDefault();
            this.closePolygon();
        }
    }

    onContextMenu(ev) {
        ev.preventDefault();
        const wrapper = this.wrapperRef.el;
        if (!wrapper) {
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
    addPolygonPoint(point) {
        if (!this.draftPolygon) {
            this.draftPolygon = [point];
        } else {
            const first = this.draftPolygon[0];
            const snap = CLOSE_SNAP_PX / this.view.zoom;
            if (
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
        if (this.draftPolygon && this.draftPolygon.length >= 3) {
            this.addShape(this.draftPolygon);
        }
        this.draftPolygon = null;
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

    hitTest(point) {
        const shapes = this.shapes;
        for (let i = shapes.length - 1; i >= 0; i--) {
            if (pointInPolygon(point, shapes[i].points)) {
                return shapes[i];
            }
        }
        return null;
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
        this.state.panel = null;
        this.updateStatus();
        this.draw();
    }

    async refreshPanel() {
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
            ["product_id", "coverage", "side_display", "quantity", "uom_id", "price_subtotal"]
        );
        if (this.selectedShape !== shape) {
            return;
        }
        this.state.panel = {
            name: shape.name || "Naamloos",
            lines,
            total: lines.reduce((sum, line) => sum + (line.price_subtotal || 0), 0),
            loading: false,
            synced: true,
        };
    }

    async removeLine(line) {
        await this.orm.unlink("tectora.roof.section.product", [line.id]);
        await this.props.record.load();
        this.refreshPanel();
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

    // ---------------------------------------------------- products via labels
    async openProducts(hit) {
        if (hit.type === "corner" && (hit.kind || "section") !== "section") {
            return; // corner products only apply to roof sections
        }
        const record = this.props.record;
        // The section/object records are created server-side from the drawing,
        // so the project must be saved (and synced) before lines can attach.
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
        const isObject = (hit.kind || "section") !== "section";
        const targetModel = isObject
            ? "tectora.roof.object"
            : "tectora.roof.section";
        const targetDomain = [
            ["project_id", "=", record.resId],
            ["canvas_ref", "=", hit.shapeId],
        ];
        let targetIds = await this.orm.search(targetModel, targetDomain, {
            limit: 1,
        });
        if (!targetIds.length) {
            // The shape was drawn but never synced: run the sync for the user
            // (same as the 'Meting bijwerken uit tekening' button) and retry.
            await this.orm.call(
                "tectora.roof.project", "action_sync_from_canvas",
                [record.resId], { context: { tectora_quiet_sync: true } }
            );
            await record.load();
            this.draw();
            targetIds = await this.orm.search(targetModel, targetDomain, {
                limit: 1,
            });
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
        const sideNumber = isSurface ? 0 : hit.edgeIndex + 1;
        const quantity = isCorner
            ? 1
            : Math.round((isSurface ? hit.areaM2 : hit.lengthM) * 100) / 100;
        const shapeName = hit.name || _t("Naamloos");
        let target;
        if (isSurface) {
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
        // Categories can restrict where their products may be used
        // ('Kan gebruikt worden voor'); unrestricted categories always show.
        let usages;
        if (isObject) {
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
        this.dialog.add(RoofProductPickerDialog, {
            title: _t("Producten toewijzen aan %s", target),
            domain: [
                ["sale_ok", "=", true],
                ["categ_id.tectora_usage", "in", [false, ...usages]],
            ],
            onConfirm: async (productIds) => {
                await this.orm.create(
                    "tectora.roof.section.product",
                    productIds.map((productId) => ({
                        [isObject ? "object_id" : "section_id"]: targetIds[0],
                        product_id: productId,
                        coverage: isCorner
                            ? "corners"
                            : isSurface
                            ? "surface"
                            : "edges",
                        edge_index: sideNumber,
                        quantity,
                    }))
                );
                await record.load();
                this.notification.add(
                    _t("Product(en) toegewezen aan %s.", target),
                    { type: "success" }
                );
                this.draw();
                this.refreshPanel();
            },
        });
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

    updateStatus() {
        if (this.draftPolygon) {
            this.state.status = `Polygoon: ${this.draftPolygon.length} punt(en) — dubbelklik of Enter om te sluiten, Esc om te annuleren`;
            return;
        }
        const shape = this.selectedShape;
        if (shape) {
            const m = this.measurements(shape.points);
            this.state.status =
                `${shape.name || "Naamloos"} — ${m.width.toFixed(2)} × ` +
                `${m.length.toFixed(2)} m, ${m.area.toFixed(2)} m², omtrek ` +
                `${m.perimeter.toFixed(2)} m · geselecteerd: sleep om te ` +
                `verplaatsen, versleep een hoekpunt om de vorm aan te passen`;
        } else {
            this.state.status =
                "Teken secties met de rechthoek- of polygoontool; de meting " +
                "wordt automatisch bijgewerkt (bij een nieuw project: eerst " +
                "opslaan). Klik op een lengte- of oppervlaktelabel of op een " +
                "hoekpunt om producten toe te voegen (wit = buitenhoek, " +
                "oranje = binnenhoek); rechtsklik om een dakobject toe te " +
                "voegen.";
        }
    }

    // -------------------------------------------------------------- drawing
    draw() {
        const canvas = this.canvasRef.el;
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

        for (const shape of this.shapes) {
            this.drawShape(ctx, shape, shape.id === this.state.selectedId);
        }
        this.labelHits = [];
        for (const shape of this.shapes) {
            this.drawShapeLabels(ctx, shape);
        }
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

        // Clickable name box at the shape's center (assigns surface
        // products), with only the area as plain text underneath.
        const m = this.measurements(points);
        const bbox = boundingBox(points);
        {
            const title =
                (style.label
                    ? `${style.label}: ${shape.name || ""}`
                    : shape.name || ""
                ).trim() || "Naamloos";
            const width = ctx.measureText(title).width + padX * 2;
            const cx = bbox.x + bbox.w / 2;
            const cy = bbox.y + bbox.h / 2 - boxHeight * 0.2;
            const x = cx - width / 2;
            const y = cy - boxHeight / 2;
            this.drawLabelBox(ctx, title, x, y, width, boxHeight, style.stroke);
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
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = "#0b1f24";
            ctx.fillText(`${m.area.toFixed(1)} m²`, cx, cy + boxHeight * 1.1);
            ctx.font = `600 ${fontSize}px sans-serif`;
        }

        if (shape.shape === "circle") {
            // One circumference label at the top plus a radius drag handle;
            // circles have no discrete edges or corners.
            const label = `${m.perimeter.toFixed(2)} m`;
            const width = ctx.measureText(label).width + padX * 2;
            const cx = bbox.x + bbox.w / 2;
            const x = cx - width / 2;
            const y = bbox.y - boxHeight / 2;
            this.drawLabelBox(ctx, label, x, y, width, boxHeight, style.stroke);
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

        // Length box on every edge.
        for (let i = 0; i < n; i++) {
            const [x1, y1] = points[i];
            const [x2, y2] = points[(i + 1) % n];
            const lengthPx = Math.hypot(x2 - x1, y2 - y1);
            if (lengthPx * zoom < EDGE_LABEL_MIN_SCREEN_PX) {
                continue;
            }
            const lengthM = lengthPx * scale;
            const label = `${lengthM.toFixed(2)} m`;
            const width = ctx.measureText(label).width + padX * 2;
            const cx = (x1 + x2) / 2;
            const cy = (y1 + y2) / 2;
            const x = cx - width / 2;
            const y = cy - boxHeight / 2;
            this.drawLabelBox(ctx, label, x, y, width, boxHeight, style.stroke);
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
            ctx.beginPath();
            ctx.arc(px, py, cornerRadius, 0, Math.PI * 2);
            ctx.fillStyle = inner ? "#d97706" : "#ffffff";
            ctx.fill();
            ctx.strokeStyle = inner ? "#92400e" : style.stroke;
            ctx.lineWidth = 1.5 / zoom;
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

    drawLabelBox(ctx, label, x, y, width, height, strokeColor) {
        const zoom = this.view.zoom;
        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(x, y, width, height, 3 / zoom);
        } else {
            ctx.rect(x, y, width, height);
        }
        ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
        ctx.fill();
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1 / zoom;
        ctx.stroke();
        ctx.fillStyle = "#0b1f24";
        ctx.fillText(label, x + width / 2, y + height / 2);
    }

    drawShape(ctx, shape, selected) {
        const style = KIND_STYLES[shape.kind] || KIND_STYLES.section;
        const points = shape.points;
        const isCircle = shape.shape === "circle";
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
    }

    drawDraftPolygon(ctx) {
        const points = this.draftPolygon;
        ctx.setLineDash([6 / this.view.zoom, 4 / this.view.zoom]);
        ctx.strokeStyle = "#0a7483";
        ctx.lineWidth = 2 / this.view.zoom;
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i][0], points[i][1]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        const r = 4 / this.view.zoom;
        ctx.fillStyle = "#0a7483";
        for (const [x, y] of points) {
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}

export const roofCanvasField = {
    component: RoofCanvasField,
    supportedTypes: ["text"],
    displayName: "Roof drawing canvas",
};

registry.category("fields").add("roof_canvas", roofCanvasField);
