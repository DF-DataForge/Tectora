/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, onWillUnmount, proxy, signal, t, useProps } from "@odoo/owl";

// Real layer thicknesses (m); the view stretches the height (exaggeration)
// so that layers of a few cm stay visible on a roof of tens of metres.
const DECK = 0.2; // the roof deck (draagvloer)
const VAPOUR = 0.004; // dampscherm
const EPDM = 0.004;
const KIMFIX_WIDTH = 0.04; // the batten bar of the kimfixatie
const KIMFIX_HEIGHT = 0.008;
const KIMFIX_OFFSET = 0.06; // from the foot of the upstand
const WALL = 0.06; // a side with an upstand but no roof edge width

const COLORS = {
    deck: [168, 168, 160],
    vapour: [64, 120, 196],
    insulation: [232, 204, 96],
    epdm: [42, 46, 52],
    // The EPDM sheets, one tint each in turn.
    sheets: [[36, 40, 48], [84, 90, 102], [38, 66, 84], [92, 72, 78]],
    edge: [176, 146, 112], // the roof edge (opstand), wood
    cap: [205, 210, 214], // its aluminium dakrand on top
    kimfix: [150, 156, 162],
    chimney: [160, 82, 64],
    dome: [190, 220, 238],
    seam: [250, 250, 250],
};

const LEGEND = [
    ["epdm", "EPDM"],
    ["insulation", "Isolatie"],
    ["vapour", "Dampscherm"],
    ["deck", "Draagvloer"],
    ["edge", "Opstand / dakrand"],
    ["cap", "Dakrandprofiel"],
    ["kimfix", "Kimfixatie (batten strip)"],
];

function signedArea(points) {
    let total = 0;
    for (let i = 0; i < points.length; i++) {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % points.length];
        total += x1 * y2 - x2 * y1;
    }
    return total / 2;
}

/**
 * A 3D view of the roof on the drawing, layer by layer: the deck, the
 * vapour barrier, the insulation on the surface inside the roof edges, the
 * EPDM on top and up the upstands, the roof edge rising its upstand above
 * the EPDM over its width, the kimfixatie at the foot of the upstands, the
 * roof objects and the seams. Drawn on a canvas (painter's algorithm, flat
 * shading); drag to turn, scroll to zoom.
 */
export class RoofView3DDialog extends Component {
    static template = "tectora_roof.RoofView3DDialog";
    static components = { Dialog };
    props = useProps({
        title: t.string(),
        model: t.object(), // {sections, objects, seams}, in metres
        close: t.function(),
    });

    setup() {
        this.canvasRef = signal.ref();
        this.state = proxy({
            yaw: -0.6,
            pitch: 0.75,
            zoom: 1,
            exaggeration: 6,
            explode: 0,
            sheets: true, // the EPDM sheets apart, with their labels
        });
        this.legend = LEGEND.map(([key, label]) => ({ key, label, color: `rgb(${COLORS[key].join(",")})` }));
        this.onMove = (ev) => this.drag(ev);
        this.onUp = () => {
            this.dragging = null;
        };
        onMounted(() => {
            window.addEventListener("pointermove", this.onMove);
            window.addEventListener("pointerup", this.onUp);
            this.render3d();
        });
        onWillUnmount(() => {
            window.removeEventListener("pointermove", this.onMove);
            window.removeEventListener("pointerup", this.onUp);
        });
    }

    // ------------------------------------------------------------ controls
    startDrag(ev) {
        this.dragging = { x: ev.clientX, y: ev.clientY, yaw: this.state.yaw, pitch: this.state.pitch };
    }

    drag(ev) {
        if (!this.dragging) {
            return;
        }
        const d = this.dragging;
        this.state.yaw = d.yaw + (ev.clientX - d.x) * 0.01;
        this.state.pitch = Math.min(1.5, Math.max(0.15, d.pitch + (ev.clientY - d.y) * 0.01));
        this.render3d();
    }

    onWheel(ev) {
        ev.preventDefault();
        this.state.zoom = Math.min(8, Math.max(0.3, this.state.zoom * (ev.deltaY < 0 ? 1.12 : 1 / 1.12)));
        this.render3d();
    }

    setValue(field, ev) {
        this.state[field] = parseFloat(ev.target.value);
        this.render3d();
    }

    toggleSheets(ev) {
        this.state.sheets = ev.target.checked;
        this.render3d();
    }

    turn(step) {
        this.state.yaw += step;
        this.render3d();
    }

    // ------------------------------------------------------------ geometry
    /** Faces of a prism over ``polygon`` from z0 to z1: top and sides
     * (outward normals), each {points, normal, color}. */
    prism(polygon, z0, z1, color, sideColor = color, faces = []) {
        if (polygon.length < 3 || z1 <= z0) {
            return faces;
        }
        const ccw = signedArea(polygon) > 0;
        faces.push({
            points: polygon.map(([x, y]) => [x, y, z1]),
            normal: [0, 0, 1],
            color,
        });
        for (let i = 0; i < polygon.length; i++) {
            const [ax, ay] = polygon[i];
            const [bx, by] = polygon[(i + 1) % polygon.length];
            const length = Math.hypot(bx - ax, by - ay) || 1;
            let nx = (by - ay) / length;
            let ny = -(bx - ax) / length;
            if (!ccw) {
                nx = -nx;
                ny = -ny;
            }
            faces.push({
                points: [[ax, ay, z0], [bx, by, z0], [bx, by, z1], [ax, ay, z1]],
                normal: [nx, ny, 0],
                color: typeof sideColor === "function" ? sideColor(i) : sideColor,
            });
        }
        return faces;
    }

    buildFaces() {
        const s = this.state;
        const E = s.exaggeration;
        const gap = s.explode * 0.4; // metres of visual gap between layers
        const faces = [];
        const lines = [];
        const labels = [];
        const z = (value) => value * E;
        let seamLevel = 0;
        for (const section of this.props.model.sections) {
            const outer = section.outer;
            const inner = section.inner || section.outer;
            const t = section.thickness;
            // Heights (visual): deck below 0, then the layers.
            const vapour0 = 0;
            const vapour1 = z(VAPOUR) + gap * 1;
            const ins0 = z(VAPOUR) + gap * 2;
            const ins1 = ins0 + z(t);
            const epdm0 = ins1 + gap;
            const epdm1 = epdm0 + z(EPDM);
            this.prism(outer, -z(DECK), 0, COLORS.deck, COLORS.deck, faces);
            this.prism(inner, vapour0 + gap * 1, vapour1, COLORS.vapour, COLORS.vapour, faces);
            this.prism(inner, ins0, ins1, COLORS.insulation, COLORS.insulation, faces);
            const sheets = section.sheets || [];
            if (s.sheets && sheets.length) {
                sheets.forEach((sheet, index) => {
                    const tint = COLORS.sheets[index % COLORS.sheets.length];
                    this.prism(sheet.points, epdm0, epdm1, tint, tint, faces);
                    const cx = sheet.points.reduce((sum, p) => sum + p[0], 0) / sheet.points.length;
                    const cy = sheet.points.reduce((sum, p) => sum + p[1], 0) / sheet.points.length;
                    labels.push({ point: [cx, cy, epdm1 + 0.02], text: sheet.label });
                });
            } else {
                this.prism(inner, epdm0, epdm1, COLORS.epdm, COLORS.epdm, faces);
            }
            // The roof edge: per side between the outline and the surface,
            // up to its upstand above the EPDM, with its profile on top; the
            // EPDM runs up its inner face; the kimfixatie at its foot.
            const n = outer.length;
            for (let i = 0; i < n; i++) {
                const a = outer[i];
                const b = outer[(i + 1) % n];
                const upstand = section.upstands[i] || 0;
                const width = section.widths[i] || 0;
                if (!upstand && !width) {
                    continue;
                }
                let ia = inner[i];
                let ib = inner[(i + 1) % n];
                if (!width) {
                    // An upstand without roof edge: a thin wall.
                    const dx = b[0] - a[0];
                    const dy = b[1] - a[1];
                    const length = Math.hypot(dx, dy) || 1;
                    const sign = signedArea(outer) > 0 ? 1 : -1;
                    const nx = (-dy / length) * sign * WALL;
                    const ny = (dx / length) * sign * WALL;
                    ia = [a[0] + nx, a[1] + ny];
                    ib = [b[0] + nx, b[1] + ny];
                }
                const top = epdm1 + z(upstand);
                const ring = [a, b, ib, ia];
                const start = faces.length;
                this.prism(ring, 0, top, COLORS.cap, (k) => (k === 2 ? COLORS.epdm : COLORS.edge), faces);
                // Layers apart: the roof edge goes see-through, so the
                // layers behind it show.
                for (let k = start; k < faces.length; k++) {
                    faces[k].alpha = 1 - s.explode * 0.75;
                }
                if (upstand) {
                    // The kimfixatie: a batten bar along the foot.
                    const dx = ib[0] - ia[0];
                    const dy = ib[1] - ia[1];
                    const length = Math.hypot(dx, dy) || 1;
                    const sign = signedArea(outer) > 0 ? 1 : -1;
                    const nx = (-dy / length) * sign;
                    const ny = (dx / length) * sign;
                    const o1 = KIMFIX_OFFSET;
                    const o2 = KIMFIX_OFFSET + KIMFIX_WIDTH;
                    const bar = [
                        [ia[0] + nx * o1, ia[1] + ny * o1],
                        [ib[0] + nx * o1, ib[1] + ny * o1],
                        [ib[0] + nx * o2, ib[1] + ny * o2],
                        [ia[0] + nx * o2, ia[1] + ny * o2],
                    ];
                    this.prism(bar, epdm1, epdm1 + z(KIMFIX_HEIGHT) + 0.01, COLORS.kimfix, COLORS.kimfix, faces);
                }
            }
            seamLevel = Math.max(seamLevel, epdm1);
        }
        for (const seam of this.props.model.seams) {
            lines.push({ points: seam.map(([x, y]) => [x, y, seamLevel + 0.005]), color: COLORS.seam });
        }
        for (const object of this.props.model.objects) {
            const base = object.base * E + gap * 4;
            if (object.kind === "skylight") {
                this.prism(object.points, base, base + 0.3 * Math.min(E, 3), COLORS.dome, COLORS.edge, faces);
            } else {
                const height = object.height || 1;
                this.prism(object.points, base, base + height * Math.min(E, 3), COLORS.chimney, COLORS.chimney, faces);
            }
        }
        return { faces, lines, labels };
    }

    // ------------------------------------------------------------- drawing
    render3d() {
        const canvas = this.canvasRef();
        if (!canvas) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.fillStyle = "#eef3f5";
        ctx.fillRect(0, 0, width, height);

        const { faces, lines, labels } = this.buildFaces();
        if (!faces.length) {
            return;
        }
        const s = this.state;
        const cy = Math.cos(s.yaw);
        const sy = Math.sin(s.yaw);
        const cp = Math.cos(s.pitch);
        const sp = Math.sin(s.pitch);
        // The model's middle is the centre of rotation.
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        for (const face of faces) {
            for (const [x, y] of face.points) {
                minX = Math.min(minX, x);
                maxX = Math.max(maxX, x);
                minY = Math.min(minY, y);
                maxY = Math.max(maxY, y);
            }
        }
        const mx = (minX + maxX) / 2;
        const my = (minY + maxY) / 2;
        const rotate = ([x, y, zz]) => {
            const rx = (x - mx) * cy - (y - my) * sy;
            const ry = (x - mx) * sy + (y - my) * cy;
            return [rx, ry * sp - zz * cp, ry * cp + zz * sp];
        };
        const view = [0, cp, sp]; // towards the viewer, after the turn
        const light = [-0.35, 0.45, 0.82];
        const projected = [];
        for (const face of faces) {
            const [nx, ny, nz] = face.normal;
            const rnx = nx * cy - ny * sy;
            const rny = nx * sy + ny * cy;
            if (rny * view[1] + nz * view[2] < -1e-3) {
                continue; // facing away
            }
            const points = face.points.map(rotate);
            const depth = points.reduce((sum, p) => sum + p[2], 0) / points.length;
            const flat = Math.abs(nz) > 0.99;
            const level = face.points.reduce((sum, p) => sum + p[2], 0) / face.points.length;
            const lit = Math.max(0, rnx * light[0] + rny * light[1] + nz * light[2]);
            const shade = 0.55 + 0.45 * lit;
            projected.push({
                points, depth, flat, level,
                alpha: face.alpha === undefined ? 1 : face.alpha,
                color: face.color.map((c) => Math.round(c * shade)),
            });
        }
        // Painter's order for a roof seen from above: the horizontal faces
        // first, lowest first (a large surface sorted by its middle would
        // cover the edges in front of it), then the vertical faces, from back
        // to front.
        projected.sort((a, b) => {
            if (a.flat !== b.flat) {
                return a.flat ? -1 : 1;
            }
            if (a.flat) {
                return a.level - b.level || a.depth - b.depth;
            }
            return a.depth - b.depth;
        });
        // Fit the model in the canvas.
        let pMinX = Infinity;
        let pMaxX = -Infinity;
        let pMinY = Infinity;
        let pMaxY = -Infinity;
        for (const face of projected) {
            for (const [x, y] of face.points) {
                pMinX = Math.min(pMinX, x);
                pMaxX = Math.max(pMaxX, x);
                pMinY = Math.min(pMinY, y);
                pMaxY = Math.max(pMaxY, y);
            }
        }
        const fit = Math.min(width / ((pMaxX - pMinX) || 1), height / ((pMaxY - pMinY) || 1)) * 0.86 * s.zoom;
        const ox = width / 2 - ((pMinX + pMaxX) / 2) * fit;
        const oy = height / 2 - ((pMinY + pMaxY) / 2) * fit;
        const screen = ([x, y]) => [ox + x * fit, oy + y * fit];
        ctx.lineJoin = "round";
        for (const face of projected) {
            ctx.beginPath();
            face.points.forEach((p, i) => {
                const [x, y] = screen(p);
                if (i) {
                    ctx.lineTo(x, y);
                } else {
                    ctx.moveTo(x, y);
                }
            });
            ctx.closePath();
            ctx.globalAlpha = face.alpha;
            ctx.fillStyle = `rgb(${face.color.join(",")})`;
            ctx.fill();
            ctx.strokeStyle = "rgba(0, 0, 0, 0.18)";
            ctx.lineWidth = 0.6;
            ctx.stroke();
            ctx.globalAlpha = 1;
        }
        ctx.setLineDash([6, 4]);
        ctx.lineWidth = 1.5;
        for (const line of lines) {
            ctx.beginPath();
            line.points.map(rotate).forEach((p, i) => {
                const [x, y] = screen(p);
                if (i) {
                    ctx.lineTo(x, y);
                } else {
                    ctx.moveTo(x, y);
                }
            });
            ctx.strokeStyle = `rgb(${line.color.join(",")})`;
            ctx.stroke();
        }
        ctx.setLineDash([]);
        // The sheets' labels.
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        for (const label of labels) {
            const [x, y] = screen(rotate(label.point));
            const w = ctx.measureText(label.text).width + 10;
            ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
            ctx.fillRect(x - w / 2, y - 9, w, 18);
            ctx.fillStyle = "#1f2937";
            ctx.fillText(label.text, x, y);
        }
    }
}
