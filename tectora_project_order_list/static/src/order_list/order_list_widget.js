import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useProjectBoardChanged } from "@tectora_project_tasks/task_phases/board_bus";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { OrderListController } from "./order_list_controller";

/**
 * Order list block of the project dashboard: progress and the next parts
 * to order. "Openen" opens the order list page.
 */
export class OrderListWidget extends Component {
    static template = "tectora_project_order_list.OrderListWidget";
    props = useProps(standardWidgetProps);

    setup() {
        this.state = proxy({ data: null });
        this.board = new OrderListController({
            env: this.env,
            orm: useService("orm"),
            action: useService("action"),
            getProjectId: () => this.props.record.resId,
        });
        onWillStart(() => this.board.load(this.state));
        useProjectBoardChanged(this.env, () => this.props.record.resId, this.board, () =>
            this.board.reload(this.state)
        );
    }

    get openLines() {
        return this.state.data.lines.filter((l) => !l.checked).slice(0, 6);
    }

    openOrderBoard() {
        return this.board.callProject(this.state, "action_tectora_open_order_board");
    }

    createOrderList() {
        return this.board.callProject(this.state, "action_tectora_create_order_list");
    }

    toggleLine(line) {
        return this.board.toggleLine(this.state, line);
    }
}

registry.category("view_widgets").add("tectora_order_list", { component: OrderListWidget });
