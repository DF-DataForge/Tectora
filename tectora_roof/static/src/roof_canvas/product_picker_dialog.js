/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Product picker for the roof canvas: the matching products are loaded once
 * and filtered client-side, with one quick-filter button per product
 * category on top.
 *
 * The same products can be assigned to more than one item at once: ticking
 * "toewijzen aan meerdere items" lists every other item of the same type in
 * the drawing (the other sides, the other surfaces, ...) to pick from.
 */
export class RoofProductPickerDialog extends Component {
    static template = "tectora_roof.RoofProductPickerDialog";
    static components = { Dialog };
    static props = {
        title: { type: String },
        domain: { type: Array },
        onConfirm: { type: Function },
        close: { type: Function },
        assignedDomain: { type: Array, optional: true },
        assignedLabel: { type: String, optional: true },
        // Quantity the assignment will get (the clicked side's length, the
        // surface in m², 1 for a corner); shown per row with the subtotal.
        quantity: { type: Number, optional: true },
        // Other items of the same type in the drawing, each
        // {key, label, detail, quantity}. Empty or absent hides the option.
        targets: { type: Array, optional: true },
        // Unit the quantities are in ("m", "m²", ""), for the totals line.
        quantityUnit: { type: String, optional: true },
        // Target keys ticked from the start: the other sides the user
        // Ctrl-selected on the drawing.
        preselectedTargets: { type: Array, optional: true },
        // How the clicked item is named in the list of what gets the products.
        baseLabel: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.assignedByProduct = {}; // product_id -> [line summaries]
        this.state = useState({
            products: [],
            activeCategory: null, // false = zonder categorie, null = alle
            search: "",
            selected: {},
            // A Ctrl-selection arrives with its extra targets already picked,
            // so the list of what gets the products is open and complete.
            multi: (this.props.preselectedTargets || []).length > 0,
            selectedTargets: Object.fromEntries(
                (this.props.preselectedTargets || []).map((key) => [key, true])
            ),
        });
        onWillStart(async () => {
            this.state.products = await this.orm.searchRead(
                "product.product",
                this.props.domain,
                ["default_code", "name", "list_price", "uom_id", "categ_id"],
                { limit: 1000, order: "default_code, name" }
            );
            if (this.props.assignedDomain) {
                const lines = await this.orm.searchRead(
                    "tectora.roof.section.product",
                    this.props.assignedDomain,
                    ["product_id", "coverage", "side_display", "quantity", "uom_id"]
                );
                for (const line of lines) {
                    const productId = line.product_id[0];
                    (this.assignedByProduct[productId] ||= []).push(
                        this.lineSummary(line)
                    );
                }
            }
        });
    }

    lineSummary(line) {
        const labels = {
            surface: "Oppervlak",
            edges: "Randen",
            corners: "Hoeken",
            drainage: "Afvoer",
            general: "Algemeen",
        };
        const parts = [labels[line.coverage] || line.coverage];
        if (line.side_display) {
            parts.push(line.side_display);
        }
        const uom = line.uom_id ? ` ${line.uom_id[1]}` : "";
        return `${parts.join(" · ")} — ${line.quantity.toFixed(2)}${uom}`;
    }

    get categories() {
        const byId = new Map();
        for (const product of this.state.products) {
            if (!product.categ_id) {
                continue;
            }
            const [id, fullName] = product.categ_id;
            const entry = byId.get(id) || {
                id,
                label: String(fullName).split(" / ").pop(),
                count: 0,
            };
            entry.count++;
            byId.set(id, entry);
        }
        return [...byId.values()].sort((a, b) => a.label.localeCompare(b.label));
    }

    get visibleProducts() {
        const query = this.state.search.trim().toLowerCase();
        const category = this.state.activeCategory;
        return this.state.products.filter((product) => {
            if (category !== null && (!product.categ_id || product.categ_id[0] !== category)) {
                return false;
            }
            if (!query) {
                return true;
            }
            return (
                product.name.toLowerCase().includes(query) ||
                (product.default_code || "").toLowerCase().includes(query)
            );
        });
    }

    // Visible products as rows, with the products already assigned to the
    // clicked shape pinned on top under their own header.
    get visibleRows() {
        const products = this.visibleProducts;
        const assigned = products.filter((p) => this.assignedByProduct[p.id]);
        const rest = products.filter((p) => !this.assignedByProduct[p.id]);
        const rows = [];
        if (assigned.length) {
            rows.push({
                key: "header-assigned",
                header: this.props.assignedLabel || "Reeds toegewezen aan dit onderdeel",
            });
            rows.push(...assigned.map((p) => ({ key: `p${p.id}`, product: p, assigned: true })));
            if (rest.length) {
                rows.push({ key: "header-rest", header: "Overige producten" });
            }
        }
        rows.push(...rest.map((p) => ({ key: `p${p.id}`, product: p, assigned: false })));
        return rows;
    }

    get selectedIds() {
        return Object.keys(this.state.selected).map(Number);
    }

    // ------------------------------------------------------- multiple items
    get targets() {
        return this.props.targets || [];
    }

    get selectedTargetKeys() {
        if (!this.state.multi) {
            return [];
        }
        return this.targets
            .filter((target) => this.state.selectedTargets[target.key])
            .map((target) => target.key);
    }

    // The clicked item plus every extra item ticked: what one product row
    // actually adds up to.
    get totalQuantity() {
        const base = this.props.quantity || 0;
        const keys = new Set(this.selectedTargetKeys);
        return this.targets.reduce(
            (total, target) => total + (keys.has(target.key) ? target.quantity : 0),
            base
        );
    }

    get itemCount() {
        return 1 + this.selectedTargetKeys.length;
    }

    toggleMulti(checked) {
        this.state.multi = checked;
        if (!checked) {
            this.state.selectedTargets = {};
        }
    }

    get baseLabel() {
        return this.props.baseLabel || "Het aangeklikte item";
    }

    toggleTarget(target) {
        if (this.state.selectedTargets[target.key]) {
            delete this.state.selectedTargets[target.key];
        } else {
            this.state.selectedTargets[target.key] = true;
        }
    }

    selectAllTargets(select) {
        this.state.selectedTargets = select
            ? Object.fromEntries(this.targets.map((target) => [target.key, true]))
            : {};
    }

    setCategory(categoryId) {
        this.state.activeCategory = categoryId;
    }

    toggle(product) {
        if (this.state.selected[product.id]) {
            delete this.state.selected[product.id];
        } else {
            this.state.selected[product.id] = true;
        }
    }

    async confirm() {
        const ids = this.selectedIds;
        const targetKeys = this.selectedTargetKeys;
        this.props.close();
        if (ids.length) {
            await this.props.onConfirm(ids, targetKeys);
        }
    }
}
