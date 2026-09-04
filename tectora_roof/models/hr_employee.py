# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    """An employee belongs to one ploeg; the team is configured here, on the
    employee, and the Employees app is organised per team."""

    _inherit = "hr.employee"

    roof_team_id = fields.Many2one(
        "tectora.roof.team",
        string="Ploeg",
        index=True,
        tracking=True,
        group_expand="_read_group_roof_team_id",
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        help="Vaste ploeg waarin deze medewerker meewerkt op de werven. Een "
        "dakproject wordt op een ploeg gepland; elk ploeglid krijgt dan zijn "
        "eigen planning-item.",
    )
    roof_team_leader_id = fields.Many2one(
        related="roof_team_id.leader_id", string="Ploegbaas"
    )
    roof_team_color = fields.Integer(related="roof_team_id.color")
    is_roof_team_leader = fields.Boolean(
        string="Is ploegbaas", compute="_compute_is_roof_team_leader",
        search="_search_is_roof_team_leader",
    )

    @api.depends("roof_team_id.leader_id")
    def _compute_is_roof_team_leader(self):
        Team = self.env["tectora.roof.team"]
        led = {}
        if self.ids:
            for team in Team.search([("leader_id", "in", self.ids)]):
                led.setdefault(team.leader_id.id, team)
        for employee in self:
            employee.is_roof_team_leader = bool(
                employee.roof_team_id.leader_id == employee
                or led.get(employee.id)
            )

    def _search_is_roof_team_leader(self, operator, value):
        leaders = self.env["tectora.roof.team"].search([]).leader_id
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", leaders.ids)]

    @api.model
    def _read_group_roof_team_id(self, teams, domain):
        """Every (active) team is a column in the employees kanban, also the
        ones nobody is on yet, so members can be dragged onto them."""
        return teams.search([], order=teams._order)
