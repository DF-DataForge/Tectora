import { Component, t, useProps } from "@odoo/owl";
import { LABELS } from "./labels";

/**
 * Compact, clickable timeline of the project phases (milestones).
 * `selectedId === false` means: all phases.
 */
export class PhaseTimeline extends Component {
    static template = "tectora_project_tasks.PhaseTimeline";
    props = useProps({
        phases: t.array(),
        selectedId: t.or([t.number(), t.boolean()]).optional(false),
        onSelect: t.function(),
        showAll: t.boolean().optional(false),
        // compact: number, name and progress only (no deadline), for narrow blocks
        compact: t.boolean().optional(false),
    });

    setup() {
        this.labels = LABELS;
    }

    get totalDone() {
        return this.props.phases.reduce((n, p) => n + p.done, 0);
    }

    get totalTasks() {
        return this.props.phases.reduce((n, p) => n + p.total, 0);
    }

    stepClass(phase) {
        const classes = [`o_tectora_step_${phase.state}`];
        if (phase.id === this.props.selectedId) {
            classes.push("o_tectora_step_selected");
        }
        if (phase.late) {
            classes.push("o_tectora_step_late");
        }
        return classes.join(" ");
    }

    stepTitle(phase) {
        let title = phase.subtitle ? `${phase.name} – ${phase.subtitle}` : phase.name;
        title += `\n${phase.done}/${phase.total} ${LABELS.tasksLower}`;
        if (phase.reached) {
            title += `\nBereikt op ${phase.reached_date}`;
        } else if (phase.deadline) {
            title += `\nDeadline ${phase.deadline}`;
        }
        return title;
    }
}
