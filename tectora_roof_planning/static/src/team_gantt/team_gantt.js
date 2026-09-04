/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onMounted, onPatched } from "@odoo/owl";

// How much taller than the standard gantt the team planner's rows are.
const ROW_SCALE = 3;

/**
 * The team planner: a click on a project block opens its summary dialog at
 * once, instead of the small popover whose "Edit" button opens it, and the
 * rows are three times as high as the standard gantt so a block can carry
 * the key data of its site. Everything else (drag, resize, create in a cell)
 * is the standard gantt.
 */
export class TectoraTeamGanttRenderer extends GanttRenderer {
    setup() {
        super.setup(...arguments);
        // Only when the rows really are taller (the constants exist on this
        // Odoo version) do the blocks get the extra height too: a taller
        // block in a standard row would spill into the next team's row.
        const tall = Boolean(this.constructor.ROW_SPAN);
        const markRoot = () => {
            for (const el of document.querySelectorAll(".o_tectora_team_gantt")) {
                el.classList.toggle("o_tectora_tall", tall);
            }
        };
        onMounted(markRoot);
        onPatched(markRoot);
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

// The gantt lays its rows out on a fine CSS grid: a row spans ROW_SPAN grid
// rows of GRID_ROW_HEIGHT pixels each (a group row GROUP_ROW_SPAN). Scaling
// the spans makes every lane taller while the grid maths stays the gantt's
// own. Left alone when a version does not expose them.
if (GanttRenderer.ROW_SPAN) {
    TectoraTeamGanttRenderer.ROW_SPAN = GanttRenderer.ROW_SPAN * ROW_SCALE;
}
if (GanttRenderer.GROUP_ROW_SPAN) {
    TectoraTeamGanttRenderer.GROUP_ROW_SPAN = Math.round(GanttRenderer.GROUP_ROW_SPAN * 1.5);
}

export const tectoraTeamGanttView = {
    ...ganttView,
    Renderer: TectoraTeamGanttRenderer,
};

registry.category("views").add("tectora_team_gantt", tectoraTeamGanttView);
