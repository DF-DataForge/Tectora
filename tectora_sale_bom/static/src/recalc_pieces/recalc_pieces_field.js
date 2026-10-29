/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// The pieces a component of a bill of materials made to measure needs, with
// their unit; hovering shows how they were calculated (the line's
// "Omrekening": m² plus the extra margin, divided by the size of one piece,
// rounded up).
export class RecalcPiecesField extends Component {
    static template = "tectora_sale_bom.RecalcPiecesField";
    props = useProps({ ...standardFieldProps });

    get value() {
        const value = this.props.record.data[this.props.name] || 0;
        const lang = (document.documentElement.lang || "nl-BE").replace("_", "-");
        try {
            return new Intl.NumberFormat(lang, { maximumFractionDigits: 2 }).format(value);
        } catch {
            return String(Math.round(value * 100) / 100);
        }
    }

    get unit() {
        const unit = this.props.record.data.pieces_uom_id;
        if (!unit) {
            return "";
        }
        return Array.isArray(unit) ? unit[1] : unit.display_name || "";
    }

    get title() {
        return this.props.record.data.tectora_recalc_info || "";
    }
}

export const recalcPiecesField = {
    component: RecalcPiecesField,
    displayName: _t("Stuks met berekening"),
    supportedTypes: ["float"],
};

registry.category("fields").add("tectora_recalc_pieces", recalcPiecesField);
