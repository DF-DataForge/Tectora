/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, onWillUnmount, proxy, signal, t, useProps } from "@odoo/owl";

import { buildScene, sceneBounds } from "./lib/scene3d";

function shade(colour, factor) {
    const match = /^#?([0-9a-f]{6})$/i.exec(colour || "");
    if (!match) {
        return colour;
    }
    const value = parseInt(match[1], 16);
    const channel = (shift) =>
        Math.max(0, Math.min(255, Math.round(((value >> shift) & 255) * factor)));
    return `rgb(${channel(16)}, ${channel(8)}, ${channel(0)})`;
}

/**
 * The rooms in 3D, looked into from above like a doll's house: the walls on
 * the viewer's side are left out, the others show their colour. Drag to turn,
 * scroll to zoom.
 */
export class Plan3DDialog extends Component {
    static template = "schldr_paint.Plan3DDialog";
    static components = { Dialog };
    props = useProps({
        document: t.object(),
        levelId: t.string(),
        colours: t.object(),
        close: t.function(),
    });

    setup() {
        this.canvasRef = signal.ref();
        this.state = proxy({ allLevels: false, showSlopes: true });
        this.camera = { yaw: -0.6, elevation: 0.75, zoom: 1 };
        this.drag = null;
        this.onResize = () => this.draw();
        onMounted(() => {
            window.addEventListener("resize", this.onResize);
            this.draw();
        });
        onWillUnmount(() => window.removeEventListener("resize", this.onResize));
    }

    get faces() {
        const levels = this.state.allLevels ? null : [this.props.levelId];
        return buildScene(this.props.document, levels, this.props.colours);
    }

    toggle(key) {
        this.state[key] = !this.state[key];
        this.draw();
    }

    draw() {
        const canvas = this.canvasRef();
        if (!canvas) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        const width = canvas.clientWidth || 800;
        const height = Math.round(Math.min(Math.max(width * 0.6, 320), window.innerHeight * 0.68));
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        canvas.style.height = `${height}px`;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const faces = this.faces.filter((face) => this.state.showSlopes || face.kind !== "slope");
        const { centre, radius } = sceneBounds(faces);
        const { yaw, elevation, zoom } = this.camera;
        const [cosYaw, sinYaw] = [Math.cos(yaw), Math.sin(yaw)];
        const [cosE, sinE] = [Math.cos(elevation), Math.sin(elevation)];
        const scale = (Math.min(width, height) / (2.3 * radius)) * zoom;
        const project = ([x, y, z]) => {
            const dx = x - centre[0];
            const dy = y - centre[1];
            const dz = z - centre[2];
            // the viewer stands at the bottom of the plan, above it: what is
            // further down the (turned) plan is nearer
            const across = dx * cosYaw - dy * sinYaw;
            const toward = dx * sinYaw + dy * cosYaw;
            return {
                x: width / 2 + across * scale,
                y: height / 2 + (toward * sinE - dz * cosE) * scale,
                depth: -toward * cosE - dz * sinE,
            };
        };

        const drawn = [];
        for (const face of faces) {
            let light = 1;
            if (face.kind === "wall") {
                // the inside of the wall has to look at the viewer: the walls
                // on the viewer's side are left out, like a doll's house
                const facing = face.normal[0] * sinYaw + face.normal[1] * cosYaw;
                if (facing < 0.02) {
                    continue;
                }
                light = 0.78 + 0.22 * Math.abs(face.normal[0] * cosYaw - face.normal[1] * sinYaw);
            } else if (face.kind === "floor") {
                light = 0.96;
            }
            const points = face.points.map(project);
            const depth = points.reduce((sum, point) => sum + point.depth, 0) / points.length;
            drawn.push({ face, points, light, depth: face.kind === "floor" ? depth + 1000 : depth });
        }
        drawn.sort((a, b) => b.depth - a.depth);
        const fill = (points, colour, alpha = 1) => {
            ctx.beginPath();
            points.forEach((point, index) =>
                index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
            );
            ctx.closePath();
            ctx.globalAlpha = alpha;
            ctx.fillStyle = colour;
            ctx.fill();
            ctx.globalAlpha = 1;
            ctx.strokeStyle = "rgba(40, 52, 64, 0.45)";
            ctx.lineWidth = 1;
            ctx.stroke();
        };
        for (const { face, points, light } of drawn) {
            fill(points, shade(face.colour, light), face.kind === "slope" ? 0.55 : 1);
            for (const decal of face.decals || []) {
                fill(decal.points.map(project), shade(decal.colour, light));
            }
        }
        if (!drawn.length) {
            ctx.fillStyle = "#6b7785";
            ctx.font = "14px Inter, Arial, sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("Nog geen ruimtes op deze verdieping.", width / 2, height / 2);
        }
    }

    onPointerDown(ev) {
        this.drag = { x: ev.clientX, y: ev.clientY, yaw: this.camera.yaw, elevation: this.camera.elevation };
        ev.target.setPointerCapture(ev.pointerId);
    }

    onPointerMove(ev) {
        if (!this.drag) {
            return;
        }
        this.camera.yaw = this.drag.yaw + (ev.clientX - this.drag.x) * 0.008;
        this.camera.elevation = Math.min(
            Math.max(this.drag.elevation + (ev.clientY - this.drag.y) * 0.006, 0.25),
            1.5
        );
        this.draw();
    }

    onPointerUp() {
        this.drag = null;
    }

    onWheel(ev) {
        ev.preventDefault();
        this.camera.zoom = Math.min(Math.max(this.camera.zoom * (ev.deltaY < 0 ? 1.12 : 1 / 1.12), 0.3), 6);
        this.draw();
    }
}
