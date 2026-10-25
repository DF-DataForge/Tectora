/** @odoo-module **/

import { SaleOrderLineListRenderer } from "@sale/js/sale_order_line_field/sale_order_line_field";
import { patch } from "@web/core/utils/patch";

// Enter on an order line (in the quantity, the price, ...) opens a new line
// right under it, in the same section, instead of moving to the next existing
// line: a quotation is typed line after line, with the new line where the
// user is working. The new line is added as "Add a line" adds it, and that
// one inserts under the line in edition (add_line_below_selection.js).
//
// Enter on a section keeps Odoo's behaviour (a new line at the top of the
// section). Enter on a new line without a product yet only leaves it (Odoo
// drops it if it is still empty), so holding Enter never stacks up empty lines.
patch(SaleOrderLineListRenderer.prototype, {
    async editNextRecord(record, group) {
        if (this.isSection(record) || !this.canCreate || !this.controls?.length) {
            return super.editNextRecord(record, group);
        }
        const isProductLine = !this.isSectionOrNote(record);
        const hasProduct = record.data.product_id || record.data.product_template_id;
        if (record.isNew && isProductLine && !hasProduct) {
            return this.props.list.leaveEditMode();
        }
        const { context } = this.controls[0];
        return this.add({ context });
    },
});
