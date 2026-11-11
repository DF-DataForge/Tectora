/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";

/**
 * The teams' free moments in the coming weeks: per team its free periods of
 * working days. With a project (opened from its dashboard) the days it
 * needs on each team, the periods long enough marked, and "Inplannen" makes
 * a concept block there.
 */
export class TectoraAvailabilityDialog extends Component {
    static template = "tectora_roof_planning.AvailabilityDialog";
    static components = { Dialog };
    props = useProps({
        projectId: t.number().optional(),
        onPlanned: t.function(),
        close: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ data: null, weeks: 8, onlyFitting: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call(
            "tectora.roof.planning", "tectora_get_availability", [],
            { project_id: this.props.projectId || false, weeks: this.state.weeks }
        );
    }

    setWeeks(ev) {
        this.state.weeks = parseInt(ev.target.value) || 8;
        return this.load();
    }

    toggleFitting(ev) {
        this.state.onlyFitting = ev.target.checked;
    }

    windows(team) {
        return this.state.onlyFitting ? team.windows.filter((w) => w.fits) : team.windows;
    }

    formatDate(value) {
        const date = new Date(`${value}T12:00:00`);
        return date.toLocaleDateString("nl-BE", { weekday: "short", day: "numeric", month: "short" });
    }

    async plan(team, window) {
        const project = this.state.data.project;
        const days = Math.min(team.needed || window.days, window.days);
        await this.orm.call("tectora.roof.planning", "tectora_plan_window", [
            project.id, team.id, window.start, days,
        ]);
        this.notification.add(`${project.name} ingepland bij ${team.name} (${days} werkdag(en), concept).`, {
            type: "success",
        });
        this.props.close();
        await this.props.onPlanned();
    }
}
