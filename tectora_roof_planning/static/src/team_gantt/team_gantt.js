/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onMounted, onPatched } from "@odoo/owl";

// How much taller than the standard gantt the team planner's blocks are.
const PILL_SCALE = 3;

// The grid tracks this renderer set itself, per grid element, and the inline
// value the gantt had put there before, so a re-render scales from the
// gantt's own layout again instead of scaling an already scaled one.
const applied = new WeakMap();

/** The grid item a pill sits in, and the grid it is placed on. */
function gridItemOf(pill, root) {
    let item = pill;
    while (item.parentElement && item !== root) {
        const display = getComputedStyle(item.parentElement).display;
        if (display === "grid" || display === "inline-grid") {
            return item;
        }
        item = item.parentElement;
    }
    return null;
}

/** The grid lines [start, end) an item covers, or null when not placed. */
function gridRowsOf(item, trackCount) {
    const style = getComputedStyle(item);
    const start = parseInt(style.gridRowStart, 10);
    if (!(start > 0)) {
        return null;
    }
    const endValue = style.gridRowEnd;
    let end;
    if (endValue.startsWith("span")) {
        end = start + (parseInt(endValue.slice(4), 10) || 1);
    } else {
        end = parseInt(endValue, 10);
        if (!(end > 0)) {
            end = start + 1;
        }
    }
    return [start, Math.min(end, trackCount + 1)];
}

/** Puts back the tracks the gantt itself set on a grid, if they are ours. */
function restoreGrid(grid) {
    const previous = applied.get(grid);
    if (previous && grid.style.gridTemplateRows === previous.value) {
        grid.style.gridTemplateRows = previous.original;
    }
    applied.delete(grid);
}

function scaleGrid(grid, tracks, covered) {
    const original = grid.style.gridTemplateRows;
    const value = tracks
        .map((size, index) => `${covered.has(index + 1) ? size * PILL_SCALE : size}px`)
        .join(" ");
    grid.style.gridTemplateRows = value;
    applied.set(grid, { original, value: grid.style.gridTemplateRows });
}

/**
 * Makes the project blocks PILL_SCALE times as high. The gantt lays a row
 * out on a fine CSS grid and places every block on a few of its tracks; the
 * tracks the blocks sit on are scaled, so a row grows with its blocks and
 * the row headers next to it (on the same tracks) follow. Empty rows and the
 * space between blocks keep the standard height. This works from the
 * rendered grid only, so it does not depend on the gantt's internals.
 */
function enlargePills(root) {
    const grids = new Map();
    for (const pill of root.querySelectorAll(".o_gantt_pill")) {
        const item = gridItemOf(pill, root);
        if (!item) {
            continue;
        }
        item.classList.add("o_tectora_pill_item");
        const grid = item.parentElement;
        if (!grids.has(grid)) {
            grids.set(grid, []);
        }
        grids.get(grid).push(item);
    }
    // Other grids of the planner (the row headers) are scaled along when they
    // have the same tracks, so they stay level with the blocks.
    const allGrids = [root, ...root.querySelectorAll("*")].filter((el) => {
        const display = getComputedStyle(el).display;
        return display === "grid" || display === "inline-grid";
    });
    for (const grid of allGrids) {
        restoreGrid(grid);
    }
    let scaled = false;
    const done = new Set();
    for (const [grid, items] of grids) {
        const tracks = getComputedStyle(grid)
            .gridTemplateRows.split(" ")
            .map((size) => parseFloat(size));
        if (!tracks.length || tracks.some((size) => !(size >= 0))) {
            continue;
        }
        const covered = new Set();
        for (const item of items) {
            const rows = gridRowsOf(item, tracks.length);
            if (!rows) {
                continue;
            }
            for (let line = rows[0]; line < rows[1]; line++) {
                covered.add(line);
            }
        }
        if (!covered.size) {
            continue;
        }
        const signature = getComputedStyle(grid).gridTemplateRows;
        for (const other of allGrids) {
            if (other !== grid && !grids.has(other) && !done.has(other)
                && getComputedStyle(other).gridTemplateRows === signature) {
                scaleGrid(other, tracks, covered);
                done.add(other);
            }
        }
        scaleGrid(grid, tracks, covered);
        done.add(grid);
        scaled = true;
    }
    root.classList.toggle("o_tectora_tall", scaled);
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
