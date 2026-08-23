/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";

// Forms whose chatter always belongs below the form, never beside it.
const BOTTOM_CHATTER_MODELS = new Set(["tectora.roof.project"]);

// Odoo puts the chatter beside the form on wide screens (mailLayout() returns
// SIDE_CHATTER from XXL up). On the roof project that column eats the width the
// drawing and its product sidebar need, so ask for the layout Odoo itself uses
// on narrower screens instead of moving the chatter around with CSS.
const AS_BOTTOM = {
    SIDE_CHATTER: "BOTTOM_CHATTER",
    // Only reachable once the form has an attachment preview, but the same
    // reasoning applies.
    EXTERNAL_COMBO_XXL: "EXTERNAL_COMBO",
};

patch(FormRenderer.prototype, {
    mailLayout(...args) {
        // mailLayout is added by the mail addon's own patch; keep working if
        // that ever stops being the case.
        const layout = super.mailLayout?.(...args);
        if (!BOTTOM_CHATTER_MODELS.has(this.props.record?.resModel)) {
            return layout;
        }
        return AS_BOTTOM[layout] || layout;
    },
});
