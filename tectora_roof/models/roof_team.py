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
    # --- the ploeg is made of contacts -----------------------------------
    partner_ids = fields.Many2many(
        "res.partner",
        "tectora_roof_team_partner_rel",
        "team_id",
        "partner_id",
        string="Ploegleden",
        help="De contacten die samen de ploeg vormen. Ze worden ingepland op "
        "de werkblokken en registreren hun uren op het portaal; een "
        "werknemersfiche is daarvoor niet nodig.",
    )
    leader_partner_id = fields.Many2one(
        "res.partner",
        string="Ploegbaas",
        help="Het contact dat de ploeg leidt; hoort altijd bij de ploeg.",
    )
    member_partner_ids = fields.Many2many(
        "res.partner",
        string="Effectieve ploeg",
        compute="_compute_member_ids",
        help="De leden van de ploeg samen met de ploegbaas. Een ploeg zonder "
        "contacten neemt de werkcontacten van haar werknemers (of van de "
        "gekozen afdeling).",
    )
    partner_count = fields.Integer(string="Aantal leden", compute="_compute_member_ids")
    # --- employees: only what needs one (timesheets, the Employees app) ---
    leader_id = fields.Many2one(
        "hr.employee", string="Ploegbaas (werknemer)",
        help="De werknemer achter de ploegbaas, als die er een is; wordt "
        "ingevuld vanuit het contact.",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Afdeling",
        help="Optioneel: als de ploeg geen eigen leden heeft, worden de "
        "medewerkers van deze afdeling als ploegleden gebruikt.",
    )
    employee_ids = fields.One2many(
        "hr.employee",
        "roof_team_id",
        string="Werknemers",
        help="De medewerkers met deze ploeg op hun werknemersfiche "
        "(Werknemers -> tab Werk -> Ploeg). Hun werkcontact wordt lid van de ploeg.",
    )
    member_ids = fields.Many2many(
        "hr.employee",
        string="Werknemers van de ploeg",
        compute="_compute_member_ids",
        help="De werknemers achter de leden van de ploeg (het contact is hun "
        "werkcontact): voor hen worden urenstaatlijnen geboekt.",
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
        help="Elk ploeglid registreert zijn eigen uren.",
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
        "partner_ids", "leader_partner_id",
        "employee_ids", "employee_ids.active", "employee_ids.work_contact_id",
        "leader_id", "department_id", "department_id.member_ids",
    )
    def _compute_member_ids(self):
        """The ploeg: its contacts and its ploegbaas. A ploeg without
        contacts falls back on the employees it had (the ploeg on the
        employee form, or its department) and their work contacts."""
        Employee = self.env["hr.employee"].sudo()
        for team in self:
            partners = team.partner_ids | team.leader_partner_id
            if partners:
                employees = Employee.search([("work_contact_id", "in", partners.ids)])
            else:
                employees = team.sudo().employee_ids
                if not employees and team.department_id:
                    employees = team.sudo().department_id.member_ids
                if team.leader_id:
                    employees |= team.sudo().leader_id
                partners = employees.work_contact_id
            team.member_partner_ids = partners
            team.partner_count = len(partners)
            team.member_ids = employees
            team.member_count = len(employees)

    # ------------------------------------------------------------ ploegbaas
    def _tectora_is_leader(self, partner):
        """``partner`` leads this ploeg."""
        leader = self._tectora_leader_partner()
        return bool(partner and leader and partner == leader)

    def _tectora_leader_partner(self):
        """The ploegbaas as a contact (none for no ploeg)."""
        team = self[:1]
        return team.leader_partner_id or team.sudo().leader_id.work_contact_id

    @api.onchange("leader_partner_id")
    def _onchange_leader_partner_id(self):
        for team in self:
            if team.leader_partner_id:
                team.partner_ids |= team.leader_partner_id

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams._tectora_sync_leader(from_employee=True)
        return teams

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("tectora_team_sync"):
            return result
        if "leader_partner_id" in vals:
            self._tectora_sync_leader()
        elif "leader_id" in vals:
            self._tectora_sync_leader(from_employee=True)
        return result

    def _tectora_sync_leader(self, from_employee=False):
        """The ploegbaas is a contact and a member; the employee behind that
        contact (if any) is kept next to it. ``from_employee``: the ploegbaas
        was set as an employee, the contact follows."""
        for team in self.with_context(tectora_team_sync=True):
            partner = team.leader_partner_id
            if from_employee and not partner:
                partner = team.sudo().leader_id.work_contact_id
                if partner:
                    team.leader_partner_id = partner
            if not partner:
                continue
            if partner not in team.partner_ids:
                team.partner_ids = [(4, partner.id)]
            employee = partner._tectora_employees()[:1]
            if team.leader_id != employee:
                team.leader_id = employee
