/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onMounted, onPatched } from "@odoo/owl";

// How much taller than the standard gantt the team planner's blocks are.
const PILL_SCALE = 3;

// The gantt (Odoo 20) lays its rows out on named grid lines: the renderer
// carries them in this variable ("[r1]25px[r2]16px[r3]25px..."), which the
// cells and the row headers both use, and a block sits between two of them
// (grid-area: r3 / c1 / r4 / c25).
const ROWS_VAR = "--Gantt__GridRows-grid-template-rows";
const PILL_HEIGHT_VAR = "--Gantt__Pill-height";

// What this planner set itself, per renderer element, and the value the
// gantt had put there before: a re-render scales from the gantt's own
// layout again instead of scaling an already scaled one.
const applied = new WeakMap();

function lineNumber(value) {
    const match = /^r(\d+)$/.exec(String(value).trim());
    return match ? parseInt(match[1], 10) : null;
}

/** The gantt's own value of a variable, undoing what this planner set. */
function ownValue(renderer, name) {
    const current = renderer.style.getPropertyValue(name);
    const previous = (applied.get(renderer) || {})[name];
    return previous && current === previous.value ? previous.original : current;
}

function setScaled(renderer, name, original, value) {
    renderer.style.setProperty(name, value);
    const state = applied.get(renderer) || {};
    state[name] = { original, value: renderer.style.getPropertyValue(name) };
    applied.set(renderer, state);
}

/**
 * Makes the project blocks PILL_SCALE times as high: the rows the blocks
 * sit on (the tracks between the lines of their grid area) are scaled in
 * the gantt's own row variable, so the row headers follow; empty rows and
 * the space between blocks keep the standard height.
 */
function enlargePills(root) {
    const renderer = root.matches(".o_gantt_renderer")
        ? root
        : root.querySelector(".o_gantt_renderer");
    if (!renderer) {
        return;
    }
    const rows = ownValue(renderer, ROWS_VAR);
    if (!rows) {
        root.classList.remove("o_tectora_tall");
        return;
    }
    const covered = new Set();
    for (const item of renderer.querySelectorAll(".o_gantt_pill_wrapper")) {
        const style = getComputedStyle(item);
        const start = lineNumber(style.gridRowStart);
        const end = lineNumber(style.gridRowEnd);
        if (start && end && end > start) {
            for (let track = start; track < end; track++) {
                covered.add(track);
            }
        }
    }
    const scaled = rows.replace(/\[r(\d+)\]\s*([\d.]+)px/g, (whole, track, size) =>
        covered.has(parseInt(track, 10)) ? `[r${track}]${parseFloat(size) * PILL_SCALE}px` : whole
    );
    setScaled(renderer, ROWS_VAR, rows, scaled);
    const pillHeight = ownValue(renderer, PILL_HEIGHT_VAR);
    if (pillHeight && scaled !== rows) {
        setScaled(renderer, PILL_HEIGHT_VAR, pillHeight, `${parseFloat(pillHeight) * PILL_SCALE}px`);
    }
    root.classList.toggle("o_tectora_tall", scaled !== rows);
}

/**
 * The team planner: a click on a project block opens its summary dialog at
 * once, instead of the small popover whose "Edit" button opens it, and the
 * blocks are three times as high as the standard gantt so they carry the
 * key data of their site on several lines. Everything else (drag, resize,
 * create in a cell) is the standard gantt.
 */
export class TectoraTeamGanttRenderer extends GanttRenderer {
    setup() {
        super.setup(...arguments);
        const enlarge = () => {
            for (const el of document.querySelectorAll(".o_tectora_team_gantt")) {
                enlargePills(el);
            }
        };
        onMounted(enlarge);
        onPatched(enlarge);
    }

    onPillClicked(ev, pill) {
        const record = pill && pill.record;
        if (record && record.id && typeof this.props.openDialog === "function") {
            if (this.popover && this.popover.isOpen) {
                this.popover.close();
            }
            this.props.openDialog({ resId: record.id });
            return;
        }
        return super.onPillClicked(ev, pill);
    }
}

export const tectoraTeamGanttView = {
    ...ganttView,
    Renderer: TectoraTeamGanttRenderer,
};

registry.category("views").add("tectora_team_gantt", tectoraTeamGanttView);
