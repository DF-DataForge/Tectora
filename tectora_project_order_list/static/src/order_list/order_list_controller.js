import { Mutex } from "@web/core/utils/concurrency";
import { notifyProjectBoardChanged } from "@tectora_project_tasks/task_phases/board_bus";

/**
 * Shared by the dashboard block and the order list page: loads the order
 * list of the project and runs the changes one after the other.
 */
export class OrderListController {
    constructor({ env, orm, action, getProjectId }) {
        this.env = env;
        this.orm = orm;
        this.action = action;
        this.getProjectId = getProjectId;
        // Changes run one by one: clicking fast must not send parallel writes.
        this.mutex = new Mutex();
    }

    async load(state) {
        const projectId = this.getProjectId();
        if (!projectId) {
            state.data = null;
            return;
        }
        state.data = await this.orm.call("project.project", "tectora_get_order_list_data", [
            [projectId],
        ]);
    }

    /** Run a change after the previous one, then reload (or open the returned action). */
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

    writeLine(state, line, values) {
        return this.mutate(state, () =>
            this.orm.write("tectora.project.order.line", [line.id], values)
        );
    }

    toggleLine(state, line) {
        line.checked = !line.checked;
        return this.writeLine(state, line, { checked: line.checked });
    }

    openLine(line) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "tectora.project.order.line",
            res_id: line.id,
            views: [[false, "form"]],
        });
    }
}
