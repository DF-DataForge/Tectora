# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    employee_ids = fields.One2many(
        "hr.employee",
        "roof_team_id",
        string="Ploegleden",
        help="De medewerkers met deze ploeg op hun werknemersfiche "
        "(Werknemers -> tab Werk -> Ploeg).",
    )
    member_ids = fields.Many2many(
        "hr.employee",
        string="Leden",
        compute="_compute_member_ids",
        help="De effectieve ploeg: de eigen ploegleden (of de leden van de "
        "gekozen afdeling) samen met de ploegbaas.",
    )
    member_count = fields.Integer(compute="_compute_member_ids")
    show_in_planner = fields.Boolean(
        string="Altijd weergeven op planner",
        help="Deze ploeg heeft altijd een rij in de planning per ploeg, ook "
        "zonder ingeplande werkblokken (tenzij ze uitgefilterd wordt), zodat "
        "er meteen in gepland kan worden.",
    )
    # Hours logging on the employee portal; both pairs are combinable.
    hours_by_leader = fields.Boolean(
        string="Door ploegleider",
        default=True,
        help="De ploegleider registreert de uren voor de volledige ploeg en "
        "bevestigt wie aanwezig was. Zonder ploegbaas mag elk ploeglid dat.",
    )
    hours_individual = fields.Boolean(
        string="Individueel",
        help="Elke medewerker registreert zijn eigen uren.",
    )
    hours_timer = fields.Boolean(
        string="Via start – stop",
        default=True,
        help="De uren lopen vanaf Start tot Stop op het portaal.",
    )
    hours_manual = fields.Boolean(
        string="Uren rechtstreeks ingeven",
        help="Het aantal uren van een dag wordt rechtstreeks ingegeven.",
    )
    note = fields.Text(string="Notities")

    @api.constrains("hours_by_leader", "hours_individual", "hours_timer", "hours_manual")
    def _check_hours_logging(self):
        for team in self:
            if not (team.hours_by_leader or team.hours_individual):
                raise ValidationError(_(
                    "Ploeg %s: kies wie de uren logt (individueel en/of door de ploegleider).",
                    team.name))
            if not (team.hours_timer or team.hours_manual):
                raise ValidationError(_(
                    "Ploeg %s: kies hoe de uren gelogd worden (start – stop en/of "
                    "rechtstreeks ingeven).", team.name))

    @api.depends(
        "employee_ids", "employee_ids.active", "leader_id", "department_id",
        "department_id.member_ids",
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
