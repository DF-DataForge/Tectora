/** @odoo-module **/

import { SaleOrderLineListRenderer } from "@sale/js/sale_order_line_field/sale_order_line_field";
import { patch } from "@web/core/utils/patch";
import { onWillRender } from "@web/owl2/utils";

// On a long quotation, the "Add a line / Add a section / Add a note / Catalog"
// row sits under the last order line, so adding a product in the middle meant
// adding it at the bottom and dragging it up. Show that row under the line the
// user last selected instead, and insert what it adds right after that line.
//
// The selected line is the last one in edition. It stays the anchor after
// leaving the row, and a line added through the row becomes the new anchor, so
// several lines can be added one after the other. The catalog opened from that
// row inserts its products there too (catalog_insert_position.js and
// sale.order._catalog_prepare_new_line_vals()). An added line left empty is
// dropped by Odoo; the anchor then falls back to the line before it. Without an
// anchor (nothing selected yet, or the line is gone) the row stays at the
// bottom, as in Odoo.

patch(SaleOrderLineListRenderer, {
    rowsTemplate: "tectora_roof.SaleOrderLineListRenderer.Rows",
});

patch(SaleOrderLineListRenderer.prototype, {
    setup() {
        super.setup();
        this.tectoraAnchorId = null;
        this.tectoraPreviousAnchorId = null;
        onWillRender(() => {
            const editedRecord = this.props.list.editedRecord;
            if (editedRecord && editedRecord.id !== this.tectoraAnchorId) {
                this.tectoraPreviousAnchorId = this.tectoraAnchorId;
                this.tectoraAnchorId = editedRecord.id;
            }
        });
    },

    /** The selected line, or the one before it, if still in the list. */
    get tectoraAnchorRecord() {
        const records = this.props.list.records;
        return (
            records.find((record) => record.id === this.tectoraAnchorId) ||
            records.find((record) => record.id === this.tectoraPreviousAnchorId)
        );
    },

    isTectoraAnchor(record) {
        return record === this.tectoraAnchorRecord;
    },

    /** The catalog button's parameters, with the selected line's position. */
    tectoraControlClickParams(control) {
        const params = control.clickParams;
        const anchor = this.tectoraAnchorRecord;
        const context = (params?.context || "{}").trim();
        if (params?.name !== "action_add_from_catalog" || !anchor || !context.startsWith("{")) {
            return params;
        }
        const list = this.props.list;
        const index = list.offset + list.records.indexOf(anchor);
        const rest = context.slice(1).trim();
        return {
            ...params,
            context: `{'tectora_catalog_after_index': ${index}${rest.startsWith("}") ? "" : ", "}${rest}`,
        };
    },

    async add(params) {
        const anchor = this.tectoraAnchorRecord;
        if (!this.canCreate || !anchor) {
            return super.add(params);
        }
        // What the x2many field does before adding a line: let pending edits
        // land, then leave the edited row (which may be the anchor itself).
        const proms = [];
        this.props.list.model.bus.trigger("NEED_LOCAL_CHANGES", { proms });
        await Promise.all(proms);
        const left = await this.props.list.leaveEditMode({ canAbandon: false });
        if (!left) {
            return;
        }
        const records = this.props.list.records;
        const index = records.indexOf(anchor);
        if (index === -1 || index === records.length - 1) {
            // Gone, or already the last line: Odoo's own add is the same thing.
            return super.add(params);
        }
        // Inserts the new line right after records[index], resequencing the
        // lines below it (as the section menu's "Add a line" does).
        await this.props.list.addNewRecordAtIndex(index, { context: params?.context });
    },
});
