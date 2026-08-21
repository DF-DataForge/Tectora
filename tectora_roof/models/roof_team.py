# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofTeam(models.Model):
    _name = "tectora.roof.team"
    _description = "Dakwerkersploeg"
    _order = "sequence, name"

    name = fields.Char(string="Ploeg", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string="Kleur")
    company_id = fields.Many2one(
        "res.company", string="Bedrijf", default=lambda self: self.env.company
    )
    leader_id = fields.Many2one("hr.employee", string="Ploegbaas")
    department_id = fields.Many2one(
        "hr.department",
        string="Afdeling",
        help="Optioneel: als de ploeg geen eigen leden heeft, worden de "
        "medewerkers van deze afdeling als ploegleden gebruikt.",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "tectora_roof_team_employee_rel",
        "team_id",
        "employee_id",
        string="Ploegleden",
    )
    member_ids = fields.Many2many(
        "hr.employee",
        string="Leden",
        compute="_compute_member_ids",
        help="De effectieve ploeg: de eigen ploegleden (of de leden van de "
        "gekozen afdeling) samen met de ploegbaas.",
    )
    member_count = fields.Integer(compute="_compute_member_ids")
    note = fields.Text(string="Notities")

    @api.depends(
        "employee_ids", "leader_id", "department_id", "department_id.member_ids"
    )
    def _compute_member_ids(self):
        for team in self:
            members = team.employee_ids
            if not members and team.department_id:
                members = team.department_id.member_ids
            if team.leader_id:
                members |= team.leader_id
            team.member_ids = members
            team.member_count = len(members)
