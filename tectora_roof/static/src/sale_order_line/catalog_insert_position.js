/** @odoo-module **/

import { ProductCatalogKanbanRecord } from "@product/product_catalog/kanban_record";
import { patch } from "@web/core/utils/patch";

// The catalog opened from under a selected order line (see
// add_line_below_selection.js) carries the line to insert its products before;
// send it along when a product is added, sale.order._update_order_line_info()
// takes it from there.
patch(ProductCatalogKanbanRecord.prototype, {
    _getUpdateQuantityAndGetPriceParams() {
        const params = super._getUpdateQuantityAndGetPriceParams();
        const beforeLineId = this.props.record.context.tectora_catalog_before_line_id;
        if (beforeLineId && params.res_model === "sale.order") {
            params.tectora_before_line_id = beforeLineId;
        }
        return params;
    },
});
