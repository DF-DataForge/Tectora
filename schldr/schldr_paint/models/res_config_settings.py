# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    schldr_deduct_min_area = fields.Float(
        related="company_id.schldr_deduct_min_area", readonly=False
    )
