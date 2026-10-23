import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { LABELS } from "./labels";
import { PhaseTimeline } from "./phase_timeline";
import { TaskBoardController } from "./task_board_controller";

/**
 * Task block of the project dashboard: the phases as a timeline, the
 * progress of the current phase and its open tasks, ticked off in place.
 * "Openen" (or a click on a phase) opens the task page.
 */
export class TaskPhasesWidget extends Component {
    static template = "tectora_project_tasks.TaskPhasesWidget";
    static components = { PhaseTimeline };
    props = useProps(standardWidgetProps);

    setup() {
        this.labels = LABELS;
        this.state = proxy({ data: null });
        this.board = new TaskBoardController(this, {
            orm: useService("orm"),
            action: useService("action"),
            getProjectId: () => this.props.record.resId,
        });
        onWillStart(() => this.board.load(this.state));
    }

    get currentPhase() {
        return this.state.data.phases.find((p) => p.state === "current");
    }

    openTaskBoard(phaseId) {
        return this.board.callProject(this.state, "action_tectora_open_task_board", [
            phaseId || false,
        ]);
    }

    startTaskPhases() {
        return this.board.callProject(this.state, "action_tectora_start_task_phases");
    }

    toggleTask(task) {
        return this.board.toggleTask(this.state, task);
    }

    openTask(task) {
        return this.board.openTask(task.id);
    }
}

export const taskPhasesWidget = {
    component: TaskPhasesWidget,
};

registry.category("view_widgets").add("tectora_task_phases", taskPhasesWidget);
