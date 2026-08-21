# -*- coding: utf-8 -*-
from odoo import fields, models


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    roof_planning_id = fields.Many2one(
        "tectora.roof.planning",
        string="Dakwerkblok",
        index=True,
        ondelete="cascade",
        copy=False,
        help="Werkblok van het dakproject waaruit deze planning-item komt.",
    )
    roof_project_id = fields.Many2one(
        related="roof_planning_id.project_id",
        string="Dakproject",
        store=True,
        index=True,
    )
    roof_team_id = fields.Many2one(
        related="roof_planning_id.team_id",
        string="Ploeg",
        store=True,
        index=True,
    )
    roof_partner_id = fields.Many2one(
        related="roof_planning_id.partner_id", string="Klant"
    )
    roof_address = fields.Char(related="roof_planning_id.address", string="Werfadres")
