import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { OrderListController } from "./order_list_controller";

const STATUS_CLASSES = {
    todo: "text-bg-light",
    stock: "text-bg-success",
    rfq: "text-bg-warning",
    ordered: "text-bg-info",
    received: "text-bg-success",
    done: "text-bg-success",
};

/** Order list page: the project's order list, worked through top to bottom. */
export class TectoraOrderBoard extends Component {
    static template = "tectora_project_order_list.OrderBoard";
    static components = { Layout };
    props = useProps(standardActionServiceProps);

    setup() {
        this.notification = useService("notification");
        this.state = proxy({ data: null, onlyOpen: false });
        this.board = new OrderListController({
            orm: useService("orm"),
            action: useService("action"),
            getProjectId: () => this.projectId,
        });
        onWillStart(() => this.board.load(this.state));
    }

    get projectId() {
        const { context, params } = this.props.action;
        return (params && params.project_id) || (context && context.active_id);
    }

    get visibleLines() {
        const lines = this.state.data.lines;
        return this.state.onlyOpen ? lines.filter((l) => !l.checked) : lines;
    }

    lineNumber(line) {
        return this.state.data.lines.indexOf(line) + 1;
    }

    statusClass(status) {
        return STATUS_CLASSES[status] || "text-bg-light";
    }

    toggleLine(line) {
        return this.board.toggleLine(this.state, line);
    }

    onSupplierChange(line, ev) {
        const value = ev.target.value;
        if (value === "other") {
            ev.target.value = line.partner_id || "";
            return this.board.openLine(line);
        }
        return this.board.writeLine(this.state, line, {
            partner_id: value ? parseInt(value) : false,
        });
    }

    onDateChange(line, field, ev) {
        return this.board.writeLine(this.state, line, { [field]: ev.target.value || false });
    }

    createPurchase(line) {
        if (!line.partner_id) {
            this.notification.add("Kies eerst een leverancier.", { type: "warning" });
            return;
        }
        return this.board.mutate(this.state, () =>
            this.board.orm.call("tectora.project.order.line", "action_tectora_create_purchase", [
                [line.id],
            ])
        );
    }

    async openPurchases(line) {
        const action = await this.board.orm.call(
            "tectora.project.order.line",
            "action_tectora_view_purchases",
            [[line.id]]
        );
        await this.board.action.doAction(action);
    }

    openLine(line) {
        return this.board.openLine(line);
    }

    openList() {
        return this.board.callProject(this.state, "action_tectora_open_order_lines");
    }

    createOrderList() {
        return this.board.callProject(this.state, "action_tectora_create_order_list");
    }

    refresh() {
        return this.board.load(this.state);
    }
}

registry.category("actions").add("tectora_project_order_list", TectoraOrderBoard);
