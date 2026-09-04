/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

/**
 * The team planner: a click on a project block opens its summary dialog at
 * once, instead of the small popover whose "Edit" button opens it. Everything
 * else (drag, resize, create in a cell) is the standard gantt.
 */
export class TectoraTeamGanttRenderer extends GanttRenderer {
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
