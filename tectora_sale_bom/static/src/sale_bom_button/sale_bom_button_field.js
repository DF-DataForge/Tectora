/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { ViewButton } from "@web/views/view_button/view_button";

// The button that opens a line's bill of materials, as one narrow column on
// the order lines. Two list buttons (muted / coloured, one hidden per line)
// form a button column Odoo lets grow wide, taking the width the description
// needs; this field shows the one icon, coloured once the line has its own
// bill of materials, and calls the same action.
export class SaleBomButtonField extends Component {
    static template = "tectora_sale_bom.SaleBomButtonField";
    static components = { ViewButton };
    props = useProps({ ...standardFieldProps });

    setup() {
        this.notification = useService("notification");
    }

    get hasOwnBom() {
        return Boolean(this.props.record.data[this.props.name]);
    }

    get title() {
        return this.hasOwnBom ? _t("Stuklijst op maat") : _t("Stuklijst aanpassen");
    }

    get onClick() {
        // As the list does for its buttons: a line that is not saved yet has
        // no bill of materials to open.
        if (!this.props.record.isNew) {
            return undefined;
        }
        return () =>
            this.notification.add(_t("Sla de offerte eerst op."), { type: "info" });
    }
}

export const saleBomButtonField = {
    component: SaleBomButtonField,
    displayName: _t("Stuklijstknop"),
    supportedTypes: ["boolean"],
    listViewWidth: 32,
};

registry.category("fields").add("tectora_sale_bom_button", saleBomButtonField);
