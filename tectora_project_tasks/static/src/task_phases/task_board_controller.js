import { Mutex } from "@web/core/utils/concurrency";
import { notifyProjectBoardChanged } from "./board_bus";

/**
 * Shared by the dashboard block and the task page: loads the task data of
 * the project and runs the project and task actions one after the other.
 */
export class TaskBoardController {
    constructor(component, { orm, action, getProjectId, onLoaded }) {
        this.component = component;
        this.env = component.env;
        this.orm = orm;
        this.action = action;
        this.getProjectId = getProjectId;
        this.onLoaded = onLoaded || (() => {});
        // Changes run one by one: clicking fast must not send parallel writes
        // on the same tasks (serialization errors on the server).
        this.mutex = new Mutex();
    }

    async load(state) {
        const projectId = this.getProjectId();
        if (!projectId) {
            state.data = null;
            return;
        }
        state.data = await this.orm.call("project.project", "tectora_get_task_board_data", [
            [projectId],
        ]);
        this.onLoaded();
    }

    /**
     * Run a change after the previous one, then reload the data. When `fn`
     * returns an action, that action is opened instead.
     */
    mutate(state, fn) {
        return this.mutex.exec(async () => {
            const result = await fn();
            if (result && typeof result === "object" && result.type) {
                return this.action.doAction(result);
            }
            await this.load(state);
            notifyProjectBoardChanged(this.env, this.getProjectId(), this);
        });
    }

    /** Reload after a change made elsewhere, in turn with this block's own changes. */
    reload(state) {
        return this.mutex.exec(() => this.load(state));
    }

    callProject(state, method, args = []) {
        return this.mutate(state, () =>
            this.orm.call("project.project", method, [[this.getProjectId()], ...args])
        );
    }

    /** Tick a task off (or reopen it), showing the result before the server confirms. */
    toggleTask(state, task, parent = null) {
        if (!task.enabled) {
            return;
        }
        const done = !task.done;
        task.done = done;
        if (done) {
            for (const child of task.children || []) {
                child.done = true;
            }
            if (parent && parent.children.every((c) => c.done)) {
                parent.done = true;
            }
        } else if (parent) {
            parent.done = false;
        }
        // Send the state the user asked for (not "toggle"), so fast clicking stays right.
        return this.mutate(state, () =>
            this.orm.call("project.task", "action_tectora_toggle_done", [[task.id]], { done })
        );
    }

    openTask(taskId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: taskId,
            views: [[false, "form"]],
        });
    }
}
