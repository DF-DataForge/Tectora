# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        copy=False,
        index=True,
        help="Roof measurement project this quotation was generated from.",
    )
