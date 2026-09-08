# -*- coding: utf-8 -*-
"""Portal access for employees.

The roofers do not need a backend seat: they get a portal login (an external
user) linked to their employee record through the standard ``user_id`` field,
so ``request.env.user.employee_id`` and the timesheets keep working. The
button on the employee form creates that user on the employee's work contact
and sends the invitation.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


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

    @api.depends("user_id", "user_id.share", "user_id.active")
    def _compute_tectora_portal_access(self):
        for employee in self:
            user = employee.user_id
            if not user or not user.active:
                employee.tectora_portal_state = "none"
            elif user.share:
                employee.tectora_portal_state = "portal"
            else:
                employee.tectora_portal_state = "internal"
            employee.tectora_portal_access = employee.tectora_portal_state == "portal"

    # ------------------------------------------------------------- portal user
    def _tectora_portal_email(self):
        self.ensure_one()
        return email_normalize(
            self.work_email or self.work_contact_id.email or self.private_email or ""
        )

    def _tectora_portal_partner(self):
        """The contact the portal user is attached to: the employee's work
        contact, created on the fly when the employee has none yet."""
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
        """Give the employee a portal login and send the invitation."""
        group_portal = self.env.ref("base.group_portal")
        group_public = self.env.ref("base.group_public")
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        for employee in self:
            if employee.user_id and employee.user_id.active:
                if employee.user_id.share:
                    raise UserError(
                        _("%s heeft al portaaltoegang (login %s).",
                          employee.name, employee.user_id.login)
                    )
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
            company = employee.company_id or self.env.company
            partner = employee._tectora_portal_partner()
            if partner.email != email:
                partner.sudo().email = email
            user = employee.user_id if employee.user_id and not employee.user_id.active else Users
            if not user:
                user = Users.search([("login", "=", email)], limit=1)
                if user and not user.share and user.active:
                    raise UserError(
                        _("Het e-mailadres %s is al de login van een interne "
                          "gebruiker; koppel die gebruiker aan de medewerker.", email)
                    )
                if user and user.partner_id != partner and user.active:
                    raise UserError(
                        _("Er bestaat al een portaalgebruiker met login %s voor een "
                          "ander contact.", email)
                    )
            if not user:
                user = Users.with_company(company).with_context(
                    no_reset_password=True
                )._create_user_from_template(
                    {
                        "email": email,
                        "login": email,
                        "partner_id": partner.id,
                        "company_id": company.id,
                        "company_ids": [(6, 0, company.ids)],
                    }
                )
            user.write(
                {
                    "active": True,
                    "company_id": company.id,
                    "company_ids": [(4, company.id)],
                    "group_ids": [(4, group_portal.id), (3, group_public.id)],
                    # the site works in the employee's timezone and language
                    "tz": employee.tz or company.partner_id.tz or user.tz,
                    "lang": company.partner_id.lang or self.env.user.lang or user.lang,
                }
            )
            employee.sudo().write({"user_id": user.id})
            employee._tectora_send_portal_invitation(user)
        return True

    def _tectora_send_portal_invitation(self, user):
        """The standard portal invitation (set your password), when the
        signup module is there; never blocks the access itself."""
        self.ensure_one()
        template = self.env.ref(
            "auth_signup.portal_set_password_email", raise_if_not_found=False
        )
        if not template:
            return False
        try:
            user.partner_id.sudo().signup_prepare()
            template.sudo().with_context(
                dbname=self.env.cr.dbname,
                lang=user.lang,
                medium="portalinvite",
                welcome_message=_(
                    "Welkom op het medewerkersportaal van %s. Na het instellen "
                    "van je wachtwoord vind je je werven onder Mijn werven.",
                    (self.company_id or self.env.company).name,
                ),
            ).send_mail(user.id, force_send=True)
        except Exception:  # pragma: no cover - mail server issues
            _logger.exception("Could not send the portal invitation to %s", user.login)
            return False
        return True

    def action_tectora_open_portal_user(self):
        self.ensure_one()
        if not self.user_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.users",
            "res_id": self.user_id.id,
            "view_mode": "form",
            "target": "current",
        }
