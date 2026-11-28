# -*- coding: utf-8 -*-
from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    roof_team_id = fields.Many2one(
        "tectora.roof.team",
        string="Ploeg",
        index=True,
        tracking=True,
        ondelete="set null",
        help="De ploeg die met dit voertuig rijdt.",
    )
