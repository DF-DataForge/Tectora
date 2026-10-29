# -*- coding: utf-8 -*-
from odoo import models


class TectoraProjectOrderLine(models.Model):
    _inherit = "tectora.project.order.line"

    def action_tectora_create_purchase(self, products=None):
        result = super().action_tectora_create_purchase(products)
        self._tectora_sync_material_list()
        return result

    def action_tectora_deliver_from_stock(self, products):
        result = super().action_tectora_deliver_from_stock(products)
        self._tectora_sync_material_list()
        return result

    def _tectora_sync_material_list(self):
        """Put what these parts ordered or take from stock on the project's
        material list: the material lines of the same product that are not
        on a live purchase order yet get the purchase order line (and its
        vendor) or the move out of the warehouse."""
        Material = self.env["tectora.roof.material"]
        for line in self:
            roof = line.project_id.roof_project_id
            if not roof:
                continue
            for product_line in line.product_line_ids:
                materials = Material.search([
                    ("project_id", "=", roof.id),
                    ("product_id", "=", product_line.product_id.id),
                ]).filtered(
                    lambda m: not m.purchase_line_id or m.purchase_line_id.state == "cancel"
                )
                purchase_line = product_line.purchase_line_id
                move = product_line.move_id
                if purchase_line and purchase_line.order_id.state != "cancel":
                    materials.write({
                        "purchase_line_id": purchase_line.id,
                        "vendor_id": purchase_line.order_id.partner_id.id,
                        "order_list_move_id": False,
                    })
                elif move and move.state != "cancel":
                    materials.filtered(lambda m: not m.order_list_move_id).write(
                        {"order_list_move_id": move.id}
                    )
