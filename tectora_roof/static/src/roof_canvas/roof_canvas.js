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
const DEFAULT_CANVAS_HEIGHT = 620;
const WHEEL_ZOOM_STEP = 1.12;
// Default real-world size (meters) of roof objects added via right-click.
const OBJECT_DEFAULT_SIZE_M = { chimney: 0.8, skylight: 1.2 };
// Circles are stored as regular polygons so measurements and the server-side
// sync keep working; 48 points keeps area/perimeter within ~0.5% of exact.
const CIRCLE_POINTS = 48;
// Ctrl-selected targets waiting for products.
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
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = useRef("canvas");
        this.wrapperRef = useRef("wrapper");
        this.mainRef = useRef("main");
        this.toolbarRef = useRef("toolbar");
        this.statusRef = useRef("status");
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
            fullscreen: false,
            // Ctrl-clicked sides, surfaces or corners waiting for Ctrl to be
            // released; they then all get the same products at once.
            multiSelect: [],
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
        // On window rather than on the canvas: the picker has to open when Ctrl
        // is released even if the focus moved to the panel in between.
        this.onWindowKeyUp = (ev) => {
            if (ev.key === "Control" || ev.key === "Meta") {
                this.flushMultiSelect();
            }
        };
        this._destroyed = false;
        this._autoSyncTimer = null;

        onMounted(() => {
            this.resizeCanvas();
            this.loadBackground();
            window.addEventListener("resize", this.onWindowResize);
            window.addEventListener("keyup", this.onWindowKeyUp);
        });
        onWillUnmount(() => {
            this._destroyed = true;
            clearTimeout(this._autoSyncTimer);
            window.removeEventListener("resize", this.onWindowResize);
            window.removeEventListener("keyup", this.onWindowKeyUp);
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
        canvas.height = this.state.fullscreen
            ? Math.max(
                  window.innerHeight -
                      (this.toolbarRef.el ? this.toolbarRef.el.offsetHeight : 0) -
                      (this.statusRef.el ? this.statusRef.el.offsetHeight : 0) -
                      6,
                  320
              )
            : DEFAULT_CANVAS_HEIGHT;
        this.fitView();
        this.draw();
    }

    toggleFullscreen() {
        this.state.fullscreen = !this.state.fullscreen;
        // The canvas is sized in pixels, so re-measure once the new layout
        // has been painted.
        requestAnimationFrame(() => this.resizeCanvas());
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

    // Pointer position in canvas pixels (the space view.x/y live in).
    canvasPoint(ev) {
        const canvas = this.canvasRef.el;
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
        const canvas = this.canvasRef.el;
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
            // Cancel the most local thing first, leave fullscreen last.
            if (this.state.contextMenu) {
                this.state.contextMenu = null;
            } else if (this.state.multiSelect.length) {
                this.clearMultiSelect();
            } else if (this.draftPolygon) {
                this.draftPolygon = null;
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
        const wrapper = this.wrapperRef.el;
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
        try {
            await this._refreshPanel();
        } catch (error) {
            console.warn("Roof canvas: could not refresh product panel", error);
        }
    }

    panelGeometry(shape) {
        if (shape.shape === "circle") {
            return { edges: [], inner: null };
        }
        const scale = this.scaleMPerPx;
        const n = shape.points.length;
        const edges = shape.points.map((point, index) => {
            const next = shape.points[(index + 1) % n];
            return {
                index,
                label: `Zijde ${index + 1}`,
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
            parts.push(_t("breedte %s m", width.toFixed(2)));
        }
        if (upstand) {
            parts.push(_t("opstand %s m", upstand.toFixed(2)));
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
            parts.push(_t("breedte %s m", edge.width.toFixed(2)));
        }
        if (edge.upstand) {
            parts.push(_t("opstand %s m", edge.upstand.toFixed(2)));
        }
        return _t(
            "Overal toepassen: %(values)s op alle %(count)s zijden. Wat hier " +
                "leeg staat, blijft op de andere zijden ongewijzigd.",
            { values: parts.join(" en "), count }
        );
    }

    setEdgeValue(key, edge, ev) {
        const shape = this.selectedShape;
        if (!shape) {
            return;
        }
        const value = parseFloat(ev.target.value);
        const values = { ...(shape[key] || {}) };
        if (value > 0) {
            values[edge.index] = Math.round(value * 100) / 100;
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
            shape.points = resizeEdgePoints(
                shape.points, index, length / this.scaleMPerPx, anchor
            );
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
        const side = hit.type === "surface" ? 0 : (hit.edgeIndex || 0) + 1;
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
        if (!["edge", "surface", "corner"].includes(hit.type)) {
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
        if (!["surface", "edge", "corner"].includes(type)) {
            return [];
        }
        const isObject = (hit.kind || "section") !== "section";
        const wantsInner = hit.cornerType === "inner";
        const targets = [];
        for (const shape of this.shapes) {
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
        // Strict whitelist: a category only shows up for the targets listed
        // in its 'Kan gebruikt worden voor'; categories without any usage
        // never appear in the canvas assignment dialog.
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
        this.dialog.add(RoofProductPickerDialog, {
            title: _t("Producten toewijzen aan %s", target),
            domain: [
                ["sale_ok", "=", true],
                ["categ_id.tectora_usage_ids.code", "in", usages],
            ],
            assignedDomain: [
                [linkField, "=", targetIds[0]],
                ["coverage", "=", coverage],
                ["edge_index", "=", sideNumber],
            ],
            assignedLabel: isSurface
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
                `verplaatsen, versleep een hoekpunt om de vorm aan te passen, ` +
                `rechtsklik op een lengtelabel om de werkelijke maat in te ` +
                `geven, stel rand en opstand per zijde in via het paneel rechts`;
        } else {
            this.state.status =
                "Teken secties met de rechthoek- of polygoontool; de meting " +
                "wordt automatisch bijgewerkt (bij een nieuw project: eerst " +
                "opslaan). Klik op een lengte- of oppervlaktelabel of op een " +
                "hoekpunt om producten toe te voegen (wit = buitenhoek, " +
                "oranje = binnenhoek). Rechtsklik op een lengtelabel om de " +
                "werkelijke maat in te geven en de tekening te kalibreren; " +
                "rechtsklik op de tekening om een dakobject toe te voegen. " +
                "Scroll om te zoomen, F voor volledig scherm.";
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

        if (shape.shape === "circle") {
            // One circumference label at the top plus a radius drag handle;
            // circles have no discrete edges or corners.
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
            const sideWidth = this.edgeWidth(shape, i);
            const sideUpstand = this.edgeUpstand(shape, i);
            let label = `${lengthM.toFixed(2)} m`;
            if (sideWidth) {
                label += ` · b ${sideWidth.toFixed(2)}`;
            }
            if (sideUpstand) {
                label += ` · h ${sideUpstand.toFixed(2)}`;
            }
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
