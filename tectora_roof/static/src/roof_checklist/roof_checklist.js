/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Checklist widget for project-level product lines: shows ALL sellable
 * products of one category (like the price-book chapter) with a checkbox.
 * Ticking creates a project line, unticking removes it, the quantity is
 * editable inline. Bound to the corresponding one2many purely as an anchor;
 * the lines are read and written through the ORM directly.
 */
export class RoofChecklistField extends Component {
    static template = "tectora_roof.RoofChecklistField";
    static props = {
        ...standardFieldProps,
        category: { type: String },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            products: [],
            lines: {}, // product_id -> line data
            search: "",
            loading: true,
        });
        onWillStart(async () => {
            await this.loadProducts();
            await this.loadLines();
            this.state.loading = false;
        });
    }

    get resId() {
        return this.props.record.resId;
    }

    get lineModel() {
        return "tectora.roof.section.product";
    }

    async loadProducts() {
        this.state.products = await this.orm.searchRead(
            "product.product",
            [
                ["sale_ok", "=", true],
                ["categ_id.name", "ilike", this.props.category],
            ],
            ["default_code", "name", "list_price", "uom_id"],
            { order: "default_code, name", limit: 500 }
        );
    }

    async loadLines() {
        const lines = {};
        if (this.resId) {
            const records = await this.orm.searchRead(
                this.lineModel,
                [
                    ["project_direct_id", "=", this.resId],
                    ["product_id.categ_id.name", "ilike", this.props.category],
                ],
                ["product_id", "quantity", "price_subtotal"]
            );
            for (const record of records) {
                lines[record.product_id[0]] = record;
            }
        }
        this.state.lines = lines;
    }

    get visibleProducts() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return this.state.products;
        }
        return this.state.products.filter(
            (product) =>
                product.name.toLowerCase().includes(query) ||
                (product.default_code || "").toLowerCase().includes(query)
        );
    }

    get checkedCount() {
        return Object.keys(this.state.lines).length;
    }

    get total() {
        return Object.values(this.state.lines).reduce(
            (sum, line) => sum + (line.price_subtotal || 0), 0
        );
    }

    async ensureSaved() {
        if (this.resId) {
            return true;
        }
        if (await this.props.record.save()) {
            return true;
        }
        this.notification.add(
            _t(
                "Sla het project eerst op (vul de verplichte velden in) " +
                "voordat je producten aanvinkt."
            ),
            { type: "warning" }
        );
        return false;
    }

    async refresh() {
        await this.loadLines();
        await this.props.record.load();
    }

    async toggle(product) {
        if (!(await this.ensureSaved())) {
            return;
        }
        const line = this.state.lines[product.id];
        if (line) {
            await this.orm.unlink(this.lineModel, [line.id]);
        } else {
            await this.orm.create(this.lineModel, [
                {
                    project_direct_id: this.resId,
                    product_id: product.id,
                    coverage: "general",
                    quantity: 1,
                },
            ]);
        }
        await this.refresh();
    }

    async setQuantity(product, ev) {
        const line = this.state.lines[product.id];
        const quantity = parseFloat(ev.target.value);
        if (!line || isNaN(quantity)) {
            return;
        }
        await this.orm.write(this.lineModel, [line.id], { quantity });
        await this.refresh();
    }
}

export const roofChecklistField = {
    component: RoofChecklistField,
    supportedTypes: ["one2many"],
    displayName: "Roof product checklist",
    extractProps: ({ options }) => ({ category: options.category || "" }),
};

registry.category("fields").add("roof_checklist", roofChecklistField);
