# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tectora_order_line_id = fields.Many2one(
        "tectora.project.order.line", string="Bestellijst-onderdeel",
        index="btree_not_null", copy=False,
        domain="[('project_id', '=', project_id)]",
    )

    def _tectora_add_order_list_lines(self, values_list):
        """Adds products of an order list part to this order and returns
        their order lines: on a request for quotation a product already on it
        gets the extra quantity, on a confirmed order a line of its own (so
        its receipt follows)."""
        self.ensure_one()
        PurchaseLine = self.env["purchase.order.line"]
        lines = PurchaseLine
        for values in values_list:
            line = PurchaseLine
            if self.state in ("draft", "sent", "to approve"):
                line = self.order_line.filtered(
                    lambda pl: not pl.display_type
                    and pl.product_id.id == values["product_id"]
                    and pl.uom_id.id == values.get("uom_id")
                )[:1]
            if line:
                line.product_qty += values["product_qty"]
            else:
                line = PurchaseLine.create(dict(values, order_id=self.id))
            lines |= line
        return lines

