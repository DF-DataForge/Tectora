# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tectora_order_line_id = fields.Many2one(
        "tectora.project.order.line", string="Bestellijst-onderdeel",
        index="btree_not_null", copy=False,
        domain="[('project_id', '=', project_id)]",
    )
