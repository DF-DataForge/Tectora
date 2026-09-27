# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    tectora_fixed_qty = fields.Boolean(
        string="Vaste hoeveelheid",
        help="De hoeveelheid geldt per orderlijn en groeit niet mee met de "
        "verkochte hoeveelheid (één container per werf, niet per m²).",
    )
