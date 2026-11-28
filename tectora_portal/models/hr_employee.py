# -*- coding: utf-8 -*-
"""Portal access of an employee: that of their work contact.

The portal runs on contacts (see ``res_partner.py``): the login, the planning
horizon and the visible segments live on the contact. An employee shows and
edits those of their work contact, and the button on the employee form gives
that contact its portal login.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    tectora_portal_access = fields.Boolean(
        string="Portaaltoegang",
        compute="_compute_tectora_portal_access",
        help="De medewerker heeft een portaallogin (externe gebruiker) en kan "
        "op /my/werven zijn werven raadplegen en uren registreren.",
    )
    tectora_portal_state = fields.Selection(
        [
            ("none", "Geen login"),
            ("portal", "Portaal"),
            ("internal", "Interne gebruiker"),
        ],
        string="Login",
        compute="_compute_tectora_portal_access",
    )
    tectora_portal_planning_horizon = fields.Selection(
        related="work_contact_id.tectora_portal_planning_horizon", readonly=False,
    )
    tectora_portal_show_overview = fields.Boolean(
        related="work_contact_id.tectora_portal_show_overview", readonly=False)
    tectora_portal_show_materials = fields.Boolean(
        related="work_contact_id.tectora_portal_show_materials", readonly=False)
    tectora_portal_show_plan = fields.Boolean(
        related="work_contact_id.tectora_portal_show_plan", readonly=False)
    tectora_portal_show_report = fields.Boolean(
        related="work_contact_id.tectora_portal_show_report", readonly=False)
    tectora_portal_show_hours = fields.Boolean(
        related="work_contact_id.tectora_portal_show_hours", readonly=False)

    @api.depends(
        "user_id", "user_id.share", "user_id.active",
        "work_contact_id.user_ids", "work_contact_id.user_ids.share",
        "work_contact_id.user_ids.active",
    )
    def _compute_tectora_portal_access(self):
        for employee in self:
            user = employee.user_id if employee.user_id.active else self.env["res.users"]
            if not user and employee.work_contact_id:
                user = employee.work_contact_id._tectora_portal_user()
            if not user:
                employee.tectora_portal_state = "none"
            elif user.share:
                employee.tectora_portal_state = "portal"
            else:
                employee.tectora_portal_state = "internal"
            employee.tectora_portal_access = employee.tectora_portal_state == "portal"

    def _tectora_portal_segments(self):
        self.ensure_one()
        return self._tectora_portal_partner()._tectora_portal_segments()

    def _tectora_portal_horizon_end(self, moment=None):
        self.ensure_one()
        return self._tectora_portal_partner()._tectora_portal_horizon_end(moment)

    def _tectora_portal_email(self):
        self.ensure_one()
        return email_normalize(
            self.work_email or self.work_contact_id.email or self.private_email or ""
        )

    def _tectora_portal_partner(self):
        """The contact the portal runs on: the employee's work contact,
        created on the fly when the employee has none yet."""
        self.ensure_one()
        partner = self.work_contact_id
        if not partner:
            partner = self.env["res.partner"].sudo().create(
                {
                    "name": self.name,
                    "email": self._tectora_portal_email() or False,
                    "phone": self.work_phone or self.mobile_phone or False,
                    "company_id": self.company_id.id,
                    "type": "contact",
                }
            )
            self.sudo().work_contact_id = partner
        return partner

    def action_tectora_grant_portal_access(self):
        """Give the employee's work contact a portal login and send the
        invitation. The login is not linked to the employee: the portal knows
        the contact, and the employee stays without a user."""
        for employee in self:
            if employee.user_id and employee.user_id.active and not employee.user_id.share:
                raise UserError(
                    _("%s is gekoppeld aan de interne gebruiker %s; die kan het "
                      "portaal met zijn gewone login gebruiken.",
                      employee.name, employee.user_id.login)
                )
            email = employee._tectora_portal_email()
            if not email:
                raise UserError(
                    _("Vul eerst een werk-e-mailadres in voor %s: dat wordt de "
                      "login van het portaal.", employee.name)
                )
            partner = employee._tectora_portal_partner()
            if email_normalize(partner.email or "") != email:
                partner.sudo().email = email
            if not partner.tz and employee.tz:
                partner.sudo().tz = employee.tz
            partner.action_tectora_grant_portal_access()
        return True

    def action_tectora_open_portal_user(self):
        self.ensure_one()
        if self.user_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "res.users",
                "res_id": self.user_id.id,
                "view_mode": "form",
                "target": "current",
            }
        return self.work_contact_id.action_tectora_open_portal_user()
