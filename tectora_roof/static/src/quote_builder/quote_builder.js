/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { RoofProductPickerDialog } from "../roof_canvas/product_picker_dialog";

/**
 * The Offerte tab of the roof project: the quotation in its standard
 * segments -- Algemene werken, Veiligheid, per roof Afbouwwerken and
 * Opbouwwerken, the other chapters, Algemene nota's -- the way the quotation
 * itself is laid out. Project lines are added, changed and removed here; the
 * drawing's products come from the drawing (per roof) and are shown with
 * where they come from.
 */
export class TectoraQuoteBuilder extends Component {
    static template = "tectora_roof.QuoteBuilder";
    props = useProps(standardWidgetProps);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = proxy({ data: null, loading: false, collapsed: {} });
        onWillStart(() => this.load());
    }

    get record() {
        return this.props.record;
    }

    async load() {
        if (!this.record.resId) {
            this.state.data = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "tectora.roof.project", "tectora_get_quote_builder", [[this.record.resId]]
            );
        } finally {
            this.state.loading = false;
        }
    }

    /** Save the form first: the lines belong to a saved project. */
    async ensureSaved() {
        if (!(await this.record.save())) {
            this.notification.add(_t("Sla het dakproject eerst op."), { type: "warning" });
            return false;
        }
        return Boolean(this.record.resId);
    }

    async afterChange() {
        await this.record.load();
        await this.load();
    }

    toggle(segment) {
        this.state.collapsed[segment.key] = !this.state.collapsed[segment.key];
    }

    isRoofSegment(segment) {
        return segment.kind === "demolition" || segment.kind === "buildup";
    }

    sourceLabel(line) {
        if (line.source === "drawing") {
            const parts = [...new Set(line.targets.map((t) =>
                t.edge_index ? `${t.name} ${t.coverage === "corners" ? "hoek" : "zijde"} ${t.edge_index}` : t.name
            ))];
            return `${line.coverage_label} · ${parts.slice(0, 3).join(", ")}${parts.length > 3 ? " …" : ""}`;
        }
        if (line.source === "order") {
            return _t("Op de offerte toegevoegd");
        }
        return line.coverage === "general" ? "" : _t("%s · volgt de meting", line.coverage_label);
    }

    addProducts(segment) {
        const domain = [["sale_ok", "=", true]];
        if (segment.category_ids.length) {
            domain.push(["categ_id", "in", segment.category_ids]);
        }
        this.dialog.add(RoofProductPickerDialog, {
            title: _t("Producten toevoegen aan %s", segment.title),
            domain,
            onConfirm: async (productIds) => {
                if (!(await this.ensureSaved())) {
                    return;
                }
                await this.orm.call(
                    "tectora.roof.project", "tectora_builder_add",
                    [[this.record.resId], segment.key, productIds]
                );
                await this.afterChange();
            },
        });
    }

    async setQuantity(line, ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        if (!(value >= 0) || !line.direct_id) {
            ev.target.value = line.quantity;
            return;
        }
        if (!(await this.ensureSaved())) {
            return;
        }
        await this.orm.write("tectora.roof.section.product", [line.direct_id], { quantity: value });
        await this.afterChange();
    }

    async removeLine(line) {
        if (!line.direct_id || !(await this.ensureSaved())) {
            return;
        }
        await this.orm.unlink("tectora.roof.section.product", [line.direct_id]);
        await this.afterChange();
    }

    async setNotes(ev) {
        await this.record.update({ quote_notes: ev.target.value });
        await this.ensureSaved();
        await this.load();
    }

    async openOrder() {
        const data = this.state.data;
        if (data && data.order_id) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "sale.order",
                res_id: data.order_id,
                views: [[false, "form"]],
            });
        }
    }
}

registry.category("view_widgets").add("tectora_quote_builder", { component: TectoraQuoteBuilder });
