# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tectora_roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        help="Het dakproject waarvan deze levering de materiaallijst (of een "
        "deel ervan) naar de werf brengt.",
    )
