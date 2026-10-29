import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useProjectBoardChanged } from "@tectora_project_tasks/task_phases/board_bus";
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
        // products: per order list line, the product list opened under it
        // ({ open, loading, items, search }).
        this.state = proxy({ data: null, onlyOpen: false, products: {} });
        this.board = new OrderListController({
            env: this.env,
            orm: useService("orm"),
            action: useService("action"),
            getProjectId: () => this.projectId,
        });
        onWillStart(() => this.board.load(this.state));
        useProjectBoardChanged(this.env, () => this.projectId, this.board, () =>
            this.board.reload(this.state)
        );
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
        return this.board
            .writeLine(this.state, line, { partner_id: value ? parseInt(value) : false })
            .then(() => {
                // Another supplier delivers other products.
                const panel = this.state.products[line.id];
                if (panel) {
                    delete this.state.products[line.id];
                    if (panel.open) {
                        return this.toggleProducts(line);
                    }
                }
            });
    }

    onDateChange(line, field, ev) {
        return this.board.writeLine(this.state, line, { [field]: ev.target.value || false });
    }

    // ------------------------------------------------------------ products

    productPanel(line) {
        return this.state.products[line.id];
    }

    async loadProducts(line) {
        this.state.products[line.id] = {
            open: true,
            loading: true,
            items: [],
            // Set apart: per purchase order, and per delivery from stock.
            ordered: [],
            stock: [],
            search: "",
            // "+ Ander product": products beyond the material list.
            extra: { open: false, term: "", results: [], loading: false },
        };
        const panel = this.state.products[line.id];
        const result = await this.board.orm.call(
            "tectora.project.order.line",
            "tectora_get_supplier_products",
            [[line.id]]
        );
        // Not when the list was dropped meanwhile (another supplier chosen).
        if (this.state.products[line.id] === panel) {
            panel.items = result.items;
            panel.ordered = result.ordered;
            panel.stock = result.stock;
            panel.loading = false;
        }
    }

    /** The products a button acts on: those selected in the list. */
    selectedPayload(line, what) {
        const selected = this.selectedProducts(line);
        if (!selected.length) {
            this.notification.add(`Selecteer eerst de producten om ${what}.`, { type: "warning" });
            return null;
        }
        return selected.map((item) => ({ product_id: item.id, quantity: item.quantity }));
    }

    /** The selected products go from the warehouse to the site. */
    async deliverFromStock(line) {
        const products = this.selectedPayload(line, "uit stock te leveren");
        if (!products) {
            return;
        }
        await this.board.mutate(this.state, () =>
            this.board.orm.call(
                "tectora.project.order.line",
                "action_tectora_deliver_from_stock",
                [[line.id], products]
            )
        );
        return this.loadProducts(line);
    }

    openRecord(model, id) {
        return this.board.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
        });
    }

    toggleProducts(line) {
        const panel = this.productPanel(line);
        if (!panel) {
            return this.loadProducts(line);
        }
        panel.open = !panel.open;
    }

    selectedProducts(line) {
        const panel = this.productPanel(line);
        return panel ? panel.items.filter((item) => item.selected) : [];
    }

    selectedCount(line) {
        const panel = this.productPanel(line);
        return panel ? this.selectedProducts(line).length : line.product_count;
    }

    visibleProducts(panel) {
        const search = panel.search.trim().toLowerCase();
        if (!search) {
            return panel.items;
        }
        return panel.items.filter((item) =>
            `${item.name} ${item.code}`.toLowerCase().includes(search)
        );
    }

    // ------------------------------------------------- other products

    toggleExtra(panel) {
        panel.extra.open = !panel.extra.open;
        if (panel.extra.open && !panel.extra.results.length) {
            return this.searchExtra(panel, "");
        }
    }

    async searchExtra(panel, term) {
        panel.extra.term = term;
        const line = this.state.data.lines.find(
            (candidate) => this.state.products[candidate.id] === panel
        );
        if (!line) {
            return;
        }
        panel.extra.loading = true;
        const results = await this.board.orm.call(
            "tectora.project.order.line",
            "tectora_search_extra_products",
            [[line.id], term]
        );
        // Only the answer to the last search counts.
        if (panel.extra.term !== term) {
            return;
        }
        const listed = new Set(panel.items.map((item) => item.id));
        panel.extra.results = results.filter((item) => !listed.has(item.id));
        panel.extra.loading = false;
    }

    onExtraInput(panel, ev) {
        const term = ev.target.value;
        clearTimeout(this.extraTimer);
        this.extraTimer = setTimeout(() => this.searchExtra(panel, term), 250);
    }

    addExtra(panel, item) {
        panel.items.unshift(item);
        panel.extra.results = panel.extra.results.filter((result) => result.id !== item.id);
    }

    toggleProduct(item) {
        item.selected = !item.selected;
    }

    setAllProducts(panel, selected) {
        for (const item of this.visibleProducts(panel)) {
            item.selected = selected;
        }
    }

    onProductQuantity(item, ev) {
        const quantity = parseFloat(String(ev.target.value).replace(",", "."));
        item.quantity = quantity > 0 ? quantity : item.quantity;
        ev.target.value = item.quantity;
        if (quantity > 0) {
            item.selected = true;
        }
    }

    createPurchase(line) {
        if (!line.partner_id) {
            this.notification.add("Kies eerst een leverancier.", { type: "warning" });
            return;
        }
        // With the product list loaded, the request for quotation holds the
        // selected products; without it, the part's products as before.
        const panel = this.productPanel(line);
        const kwargs = {};
        if (panel && !panel.loading && panel.items.length) {
            const products = this.selectedPayload(line, "te bestellen");
            if (!products) {
                panel.open = true;
                return;
            }
            kwargs.products = products;
        }
        return this.board.mutate(this.state, () =>
            this.board.orm.call(
                "tectora.project.order.line",
                "action_tectora_create_purchase",
                [[line.id]],
                kwargs
            )
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
