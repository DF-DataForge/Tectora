# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


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

    dropship_pickup_order_ids = fields.Many2many(
        "purchase.order",
        string="Dropship-orders met afhaling",
        compute="_compute_dropship_pickup_info",
    )
    dropship_pickup_info = fields.Text(
        string="Af te halen aan het magazijn",
        compute="_compute_dropship_pickup_info",
        help="Wat de ploeg aan het magazijn ophaalt naast de dropship-"
        "leveringen op de werf, zoals vermeld op die inkooporders.",
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

    def action_organize_purchases(self):
        """The ordering board of this project: one column per logistic
        route, cards dragged from one to the other, vendors and stock on
        every card, and the purchase orders made from there."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "tectora_purchase.action_tectora_material_organize"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["display_name"] = _("Inkoop organiseren — %s", self.display_name)
        action["context"] = {
            "default_project_id": self.id,
            "search_default_open": 1,
        }
        return action

    @api.depends(
        "material_line_ids.purchase_order_id.tectora_warehouse_pickup",
        "material_line_ids.purchase_order_id.state",
    )
    def _compute_dropship_pickup_info(self):
        for project in self:
            orders = project.material_line_ids.purchase_order_id.filtered(
                lambda o: o.tectora_warehouse_pickup and o.state != "cancel"
            )
            orders |= self.env["purchase.order"].search(
                [
                    ("tectora_roof_project_id", "=", project.id),
                    ("tectora_warehouse_pickup", "=", True),
                    ("state", "!=", "cancel"),
                ]
            )
            project.dropship_pickup_order_ids = orders
            project.dropship_pickup_info = "\n\n".join(
                "%s: %s" % (order.name, order.tectora_warehouse_pickup_note or "")
                for order in orders
            )
