/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
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
// Candidate grid spacings in meters; the smallest one that renders at a
// readable on-screen distance is used, minor lines every step, major every 5.
const GRID_STEPS_M = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
const GRID_MIN_SCREEN_PX = 30;
const GRID_MAJOR_EVERY = 5;
// Edges shorter than this on screen don't get a length box (unreadable).
const EDGE_LABEL_MIN_SCREEN_PX = 34;

const KIND_STYLES = {
    section: { fill: "rgba(10, 116, 131, 0.28)", stroke: "#0a7483", label: "" },
    chimney: { fill: "rgba(217, 119, 6, 0.35)", stroke: "#b45309", label: "Schoorsteen" },
    skylight: { fill: "rgba(37, 99, 235, 0.30)", stroke: "#1d4ed8", label: "Koepel" },
};

function polygonArea(points) {
    let total = 0;
    const n = points.length;
    for (let i = 0; i < n; i++) {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % n];
        total += x1 * y2 - x2 * y1;
    }
    return Math.abs(total) / 2;
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
        });
        this.world = { ...DEFAULT_WORLD };
        this.view = { zoom: 1, x: 0, y: 0 };
        this.backgroundImage = null;
        this.drag = null; // {mode: 'move'|'rect'|'pan', ...}
        this.draftPolygon = null; // [[x, y], ...]
        this._rawCache = undefined;
        this._shapes = [];
        this.edgeHits = []; // clickable edge-length boxes, in world coordinates

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
        this.props.record.update({ [this.props.name]: raw });
        this.draw();
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
        const wrapper = this.wrapperRef.el;
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
            const edgeHit = this.edgeHitTest(point);
            if (edgeHit) {
                this.openEdgeProducts(edgeHit);
                return;
            }
            const hit = this.hitTest(point);
            this.state.selectedId = hit ? hit.id : null;
            if (hit) {
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
        }
    }

    onPointerMove(ev) {
        if (!this.drag) {
            if (this.state.tool === "select" && this.canvasRef.el) {
                const hover = this.edgeHitTest(this.toWorld(ev));
                this.canvasRef.el.style.cursor = hover ? "pointer" : "";
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
        } else if (this.drag.mode === "move") {
            const dx = point[0] - this.drag.start[0];
            const dy = point[1] - this.drag.start[1];
            if (Math.abs(dx) + Math.abs(dy) > 1) {
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
            this.updateStatus();
            this.draw();
        } else if (ev.key === "Enter" && this.draftPolygon) {
            ev.preventDefault();
            this.closePolygon();
        }
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

    addShape(points) {
        const sectionCount =
            this.shapes.filter((s) => (s.kind || "section") === "section").length + 1;
        this._shapes = [
            ...this.shapes,
            {
                id: makeId(),
                kind: "section",
                name: `Sectie ${sectionCount}`,
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

    edgeHitTest([px, py]) {
        for (let i = this.edgeHits.length - 1; i >= 0; i--) {
            const hit = this.edgeHits[i];
            if (
                px >= hit.x && px <= hit.x + hit.w &&
                py >= hit.y && py <= hit.y + hit.h
            ) {
                return hit;
            }
        }
        return null;
    }

    // ------------------------------------------------------- edge products
    async openEdgeProducts(edge) {
        if ((edge.kind || "section") !== "section") {
            this.notification.add(
                _t("Producten kunnen alleen aan daksecties worden gekoppeld."),
                { type: "warning" }
            );
            return;
        }
        const record = this.props.record;
        // The section records are created server-side from the drawing, so the
        // project must be saved (and synced) before lines can be attached.
        if (!(await record.save())) {
            return;
        }
        const sectionIds = await this.orm.search(
            "tectora.roof.section",
            [
                ["project_id", "=", record.resId],
                ["canvas_ref", "=", edge.shapeId],
            ],
            { limit: 1 }
        );
        if (!sectionIds.length) {
            this.notification.add(
                _t(
                    "Er bestaat nog geen sectie voor deze vorm. Klik eerst op " +
                    "'Meting bijwerken uit tekening'."
                ),
                { type: "warning" }
            );
            return;
        }
        const quantity = Math.round(edge.lengthM * 100) / 100;
        this.dialog.add(SelectCreateDialog, {
            resModel: "product.product",
            title: _t("Producten voor rand van %(section)s — %(length)s m", {
                section: edge.name || _t("sectie"),
                length: quantity.toFixed(2),
            }),
            domain: [["sale_ok", "=", true]],
            multiSelect: true,
            onSelected: async (productIds) => {
                await this.orm.create(
                    "tectora.roof.section.product",
                    productIds.map((productId) => ({
                        section_id: sectionIds[0],
                        product_id: productId,
                        coverage: "edges",
                        quantity,
                    }))
                );
                await record.load();
                this.notification.add(
                    _t("Product(en) toegevoegd aan sectie '%s'.", edge.name),
                    { type: "success" }
                );
                this.draw();
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
                `${m.perimeter.toFixed(2)} m`;
        } else {
            this.state.status =
                "Teken secties met de rechthoek- of polygoontool. Klik daarna op " +
                "'Meting bijwerken uit tekening' om de secties aan te maken. " +
                "Klik op een lengtelabel op een rand om producten aan die rand " +
                "toe te voegen.";
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
        this.edgeHits = [];
        for (const shape of this.shapes) {
            this.drawEdgeLabels(ctx, shape);
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

    drawEdgeLabels(ctx, shape) {
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
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(x, y, width, boxHeight, 3 / zoom);
            } else {
                ctx.rect(x, y, width, boxHeight);
            }
            ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
            ctx.fill();
            ctx.strokeStyle = style.stroke;
            ctx.lineWidth = 1 / zoom;
            ctx.stroke();
            ctx.fillStyle = "#0b1f24";
            ctx.fillText(label, cx, cy);
            this.edgeHits.push({
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
    }

    drawShape(ctx, shape, selected) {
        const style = KIND_STYLES[shape.kind] || KIND_STYLES.section;
        const points = shape.points;
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i][0], points[i][1]);
        }
        ctx.closePath();
        ctx.fillStyle = style.fill;
        ctx.fill();
        ctx.strokeStyle = selected ? "#111827" : style.stroke;
        ctx.lineWidth = (selected ? 3 : 2) / this.view.zoom;
        ctx.stroke();

        if (selected) {
            const r = 4 / this.view.zoom;
            ctx.fillStyle = "#ffffff";
            for (const [x, y] of points) {
                ctx.beginPath();
                ctx.arc(x, y, r, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
        }

        // Label with real-world measurements
        const m = this.measurements(points);
        const box = boundingBox(points);
        const cx = box.x + box.w / 2;
        const cy = box.y + box.h / 2;
        const fontSize = 13 / this.view.zoom;
        ctx.font = `600 ${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = "#0b1f24";
        const title = style.label
            ? `${style.label}: ${shape.name || ""}`.trim()
            : shape.name || "";
        if (title) {
            ctx.fillText(title, cx, cy - fontSize * 0.4);
        }
        ctx.font = `${fontSize}px sans-serif`;
        ctx.fillText(
            `${m.width.toFixed(1)} × ${m.length.toFixed(1)} m — ${m.area.toFixed(1)} m²`,
            cx,
            cy + fontSize * 0.9
        );
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
