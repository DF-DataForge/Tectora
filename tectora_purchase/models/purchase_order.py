# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tectora_roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        index=True,
        copy=False,
        ondelete="set null",
        help="Het dakproject waarvan de materiaalbehoefte met deze order "
        "besteld wordt.",
    )
    tectora_logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        copy=False,
        help="Dropship naar de werf of levering aan het magazijn; bepaalt de "
        "operatie en het leveradres van de order.",
    )
    tectora_material_count = fields.Integer(
        string="Materiaallijnen", compute="_compute_tectora_material_count"
    )

    @api.depends("order_line.tectora_material_ids")
    def _compute_tectora_material_count(self):
        for order in self:
            order.tectora_material_count = len(order.order_line.tectora_material_ids)

    def action_view_tectora_materials(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaalbehoefte"),
            "res_model": "tectora.roof.material",
            "view_mode": "list,form",
            "domain": [("purchase_order_id", "=", self.id)],
            "context": {"search_default_group_project": 1},
        }


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    tectora_material_ids = fields.One2many(
        "tectora.roof.material",
        "purchase_line_id",
        string="Materiaalbehoefte",
        help="De materiaallijnen van de dakprojecten die met deze lijn "
        "besteld worden.",
    )
