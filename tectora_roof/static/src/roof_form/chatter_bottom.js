/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";

// Forms whose chatter always belongs below the form, never beside it: the
// ones whose root <form> carries this class (the roof project and the project
// dashboard).
const BOTTOM_CHATTER_CLASS = "o_tectora_chatter_bottom";

function wantsBottomChatter(renderer) {
    const xmlDoc = renderer.props.archInfo?.xmlDoc;
    const classes = xmlDoc?.getAttribute?.("class") || "";
    return classes.split(/\s+/).includes(BOTTOM_CHATTER_CLASS);
}

// Odoo puts the chatter beside the form on wide screens (mailLayout() returns
// SIDE_CHATTER from XXL up). On the roof project that column eats the width the
// drawing and its product sidebar need, so ask for the layout Odoo itself uses
// on narrower screens.
//
// This is half of the fix. It drops the o-aside class, which is what makes the
// chatter a fixed-width column, but not the row: form_compiler.js keeps the
// renderer "flex-nowrap" from XXL up whatever the chatter's layout is, so the
// direction is turned back in roof_canvas.scss.
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
        if (!wantsBottomChatter(this)) {
            return layout;
        }
        return AS_BOTTOM[layout] || layout;
    },
});
