import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useProjectBoardChanged } from "./board_bus";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { LABELS } from "./labels";
import { PhaseTimeline } from "./phase_timeline";
import { TaskBoardController } from "./task_board_controller";

/** Task page: a compact phase timeline on top, the tasks of the chosen phase below. */
export class TectoraTasksBoard extends Component {
    static template = "tectora_project_tasks.TasksBoard";
    static components = { Layout, PhaseTimeline };
    props = useProps(standardActionServiceProps);

    setup() {
        this.labels = LABELS;
        this.state = proxy({
            data: null,
            phaseId: undefined,
            onlyOpen: false,
            showDisabled: false,
        });
        this.board = new TaskBoardController(this, {
            orm: useService("orm"),
            action: useService("action"),
            getProjectId: () => this.projectId,
            onLoaded: () => this.onLoaded(),
        });
        onWillStart(() => this.board.load(this.state));
        useProjectBoardChanged(this.env, () => this.projectId, this.board, () =>
            this.board.reload(this.state)
        );
    }

    get params() {
        return this.props.action.params || {};
    }

    get projectId() {
        const { context } = this.props.action;
        return this.params.project_id || (context && context.active_id);
    }

    onLoaded() {
        const phases = this.state.data.phases;
        if (this.state.phaseId === undefined) {
            const requested = this.params.phase_id;
            const current = phases.find((p) => p.state === "current");
            this.state.phaseId = requested || (current ? current.id : false);
        }
        if (this.state.phaseId && !phases.some((p) => p.id === this.state.phaseId)) {
            this.state.phaseId = false;
        }
    }

    get visiblePhases() {
        const phases = this.state.data.phases;
        return this.state.phaseId ? phases.filter((p) => p.id === this.state.phaseId) : phases;
    }

    tasksOf(phase) {
        return phase.tasks.filter(
            (t) => (t.enabled || this.state.showDisabled) && (!this.state.onlyOpen || !t.done)
        );
    }

    get disabledOptionCount() {
        return this.visiblePhases.reduce((n, p) => n + p.tasks.filter((t) => !t.enabled).length, 0);
    }

    selectPhase(phaseId) {
        this.state.phaseId = phaseId;
    }

    toggleTask(task, parent = null) {
        return this.board.toggleTask(this.state, task, parent);
    }

    toggleTaskEnabled(task) {
        task.enabled = !task.enabled;
        return this.board.mutate(this.state, () =>
            this.board.orm.call("project.task", "action_tectora_toggle_enabled", [[task.id]])
        );
    }

    togglePhaseReached(phase) {
        return this.board.callProject(this.state, "action_tectora_toggle_phase_reached", [
            phase.milestone_id,
        ]);
    }

    startTaskPhases() {
        return this.board.callProject(this.state, "action_tectora_start_task_phases");
    }

    openList() {
        const milestoneId = this.state.phaseId ? this.visiblePhases[0].milestone_id : false;
        return this.board.callProject(this.state, "action_tectora_open_phase_tasks", [milestoneId]);
    }

    openTask(task) {
        return this.board.openTask(task.id);
    }

    openLink(task) {
        return this.board.callProject(this.state, task.link.method);
    }

    refresh() {
        return this.board.load(this.state);
    }
}

registry.category("actions").add("tectora_project_tasks", TectoraTasksBoard);
