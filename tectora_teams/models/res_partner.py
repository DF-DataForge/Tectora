# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    roof_team_ids = fields.Many2many(
        "tectora.roof.team",
        "tectora_roof_team_partner_rel",
        "partner_id",
        "team_id",
        string="Ploegen",
        help="De ploegen waar dit contact lid van is.",
    )
    roof_team_count = fields.Integer(compute="_compute_roof_team_count")

    @api.depends("roof_team_ids")
    def _compute_roof_team_count(self):
        for partner in self:
            partner.roof_team_count = len(partner.roof_team_ids)
