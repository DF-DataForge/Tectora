# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class TectoraRoofTeam(models.Model):
    """The ploeg's app: its contacts (the ploeg itself lives in the roofing
    core, where it is made of contacts) and its vehicles from Fleet."""

    _inherit = "tectora.roof.team"

    vehicle_ids = fields.One2many(
        "fleet.vehicle", "roof_team_id", string="Voertuigen",
        help="De voertuigen van het wagenpark die aan deze ploeg toegewezen zijn.",
    )
    vehicle_count = fields.Integer(string="Aantal voertuigen", compute="_compute_vehicle_count")

    @api.depends("vehicle_ids")
    def _compute_vehicle_count(self):
        for team in self:
            team.vehicle_count = len(team.vehicle_ids)

    # -------------------------------------------------------------- buttons
    def action_view_partners(self):
        self.ensure_one()
        partners = self.member_partner_ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Leden van %s", self.display_name),
            "res_model": "res.partner",
            "view_mode": "kanban,list,form",
            "domain": [("id", "in", partners.ids)],
            "context": {"default_roof_team_ids": [(4, self.id)]},
        }

    def action_view_vehicles(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Voertuigen van %s", self.display_name),
            "res_model": "fleet.vehicle",
            "view_mode": "kanban,list,form",
            "domain": [("roof_team_id", "=", self.id)],
            "context": {"default_roof_team_id": self.id},
        }
