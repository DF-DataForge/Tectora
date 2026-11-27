# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class TectoraRoofTeam(models.Model):
    """A ploeg made of contacts, with its vehicles.

    The contacts are the ploeg. What works per employee (the planner's work
    blocks, the portal, timesheets) takes the employees behind those
    contacts: ``member_ids`` are the employees whose work contact is one of
    the ploeg's contacts. A ploeg without contacts keeps the employees it
    had (the ploeg on the employee form, or its department)."""

    _inherit = "tectora.roof.team"

    partner_ids = fields.Many2many(
        "res.partner",
        "tectora_roof_team_partner_rel",
        "team_id",
        "partner_id",
        string="Ploegleden (contacten)",
        help="De contacten die samen de ploeg vormen. Wie ook werknemer is "
        "(dit contact is zijn werkcontact), staat mee op de werkblokken van "
        "de planner en op het medewerkersportaal.",
    )
    leader_partner_id = fields.Many2one(
        "res.partner",
        string="Ploegbaas",
        help="Het contact dat de ploeg leidt; hoort altijd bij de ploeg.",
    )
    partner_count = fields.Integer(string="Aantal leden", compute="_compute_partner_count")
    vehicle_ids = fields.One2many(
        "fleet.vehicle", "roof_team_id", string="Voertuigen",
        help="De voertuigen van het wagenpark die aan deze ploeg toegewezen zijn.",
    )
    vehicle_count = fields.Integer(string="Aantal voertuigen", compute="_compute_vehicle_count")

    @api.depends("partner_ids", "leader_partner_id")
    def _compute_partner_count(self):
        for team in self:
            team.partner_count = len(team.partner_ids | team.leader_partner_id)

    @api.depends("vehicle_ids")
    def _compute_vehicle_count(self):
        for team in self:
            team.vehicle_count = len(team.vehicle_ids)

    # An overriding compute replaces the dependencies: the base ones too.
    @api.depends(
        "employee_ids", "employee_ids.active", "leader_id", "department_id",
        "department_id.member_ids", "partner_ids", "leader_partner_id",
    )
    def _compute_member_ids(self):
        """The employees of the ploeg: those behind its contacts; without
        contacts, the employees it had."""
        super()._compute_member_ids()
        Employee = self.env["hr.employee"].sudo()
        for team in self:
            partners = team.partner_ids | team.leader_partner_id
            if not partners:
                continue
            members = Employee.search([("work_contact_id", "in", partners.ids)])
            team.member_ids = members
            team.member_count = len(members)

    # ------------------------------------------------------------ ploegbaas
    def _tectora_leader_employee(self, partner):
        """The employee behind a contact (its work contact), if any."""
        if not partner:
            return self.env["hr.employee"]
        return self.env["hr.employee"].sudo().search(
            [("work_contact_id", "=", partner.id)], limit=1
        )

    @api.onchange("leader_partner_id")
    def _onchange_leader_partner_id(self):
        for team in self:
            if team.leader_partner_id:
                team.partner_ids |= team.leader_partner_id

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams._tectora_sync_leader()
        return teams

    def write(self, vals):
        result = super().write(vals)
        if "leader_partner_id" in vals and not self.env.context.get("tectora_team_sync"):
            self._tectora_sync_leader()
        return result

    def _tectora_sync_leader(self):
        """The ploegbaas is a member, and -- where the contact is an
        employee -- the ploegbaas of everything that works per employee."""
        for team in self.with_context(tectora_team_sync=True):
            partner = team.leader_partner_id
            if not partner:
                continue
            if partner not in team.partner_ids:
                team.partner_ids = [(4, partner.id)]
            employee = team._tectora_leader_employee(partner)
            if employee and team.leader_id != employee:
                team.leader_id = employee

    # -------------------------------------------------------------- buttons
    def action_view_partners(self):
        self.ensure_one()
        partners = self.partner_ids | self.leader_partner_id
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
