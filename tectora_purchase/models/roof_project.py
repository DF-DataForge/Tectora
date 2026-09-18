# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    material_to_order_count = fields.Integer(
        string="Te bestellen", compute="_compute_material_to_order_count"
    )

    @api.depends(
        "material_line_ids.purchase_state",
        "material_line_ids.product_id",
        "material_line_ids.quantity",
    )
    def _compute_material_to_order_count(self):
        for project in self:
            project.material_to_order_count = len(
                project.material_line_ids._lines_to_order()
            )

    def _tectora_delivery_partner(self):
        """Where a dropship for this project goes: the delivery address of the
        order, else the customer."""
        self.ensure_one()
        order = self.sale_order_id
        partner = order.partner_shipping_id if order else self.env["res.partner"]
        return partner or self.partner_id

    def _get_purchase_orders(self):
        """Purchase orders of the project: the ones carrying its analytic
        account (as before) and the ones created from its material list, so
        the Inkoop button is right even before the project has an analytic
        account."""
        orders = super()._get_purchase_orders()
        linked = self.env["purchase.order"].search(
            [("tectora_roof_project_id", "=", self.id)]
        )
        if orders is None:
            return linked
        return orders | linked

    def action_create_purchase_orders(self):
        """Order the material of this roof project that is not ordered yet."""
        self.ensure_one()
        return self.material_line_ids.action_create_purchase_orders()
