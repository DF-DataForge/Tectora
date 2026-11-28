# -*- coding: utf-8 -*-
"""The portal runs on contacts.

Whoever works on the sites is a contact: a member of a ploeg, planned on the
work blocks. That contact gets a portal login (an external user, no backend
seat, no employee record needed) and finds their sites on /my/werven, where
they register their hours. A contact that is also an employee (it is the
employee's work contact) gets timesheet lines for those hours on top.
"""
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    tectora_portal_access = fields.Boolean(
        string="Portaaltoegang",
        compute="_compute_tectora_portal_access",
        help="Dit contact heeft een portaallogin (externe gebruiker) en kan "
        "op /my/werven zijn werven raadplegen en uren registreren.",
    )
    tectora_portal_state = fields.Selection(
        [
            ("none", "Geen login"),
            ("portal", "Portaal"),
            ("internal", "Interne gebruiker"),
        ],
        string="Portaallogin",
        compute="_compute_tectora_portal_access",
    )
    tectora_is_worker = fields.Boolean(
        string="Werkt op de werven",
        compute="_compute_tectora_is_worker",
        help="Lid of ploegbaas van een ploeg, ingepland op een werkblok, of "
        "werknemer.",
    )
    tectora_portal_planning_horizon = fields.Selection(
        [("week", "1 week"), ("month", "1 maand"), ("all", "Alles")],
        string="Planning op het portaal",
        default="all",
        required=True,
        help="Hoe ver vooruit deze persoon de planning ziet op het portaal: "
        "werkblokken die later beginnen, en werven die hij alleen via zo'n "
        "werkblok zou zien, blijven verborgen tot ze binnen die termijn "
        "vallen. Wat al voorbij is of vandaag loopt, blijft zichtbaar.",
    )
    # Which segments of a site this person sees on the portal.
    tectora_portal_show_overview = fields.Boolean(
        string="Overzicht", default=True,
        help="Tab Overzicht: werf, ploeg en planning, werfinfo.")
    tectora_portal_show_materials = fields.Boolean(
        string="Materialen", default=True, help="Tab Materialen: de materiaallijst van de werf.")
    tectora_portal_show_plan = fields.Boolean(
        string="Plan", default=True, help="Tab Plan: het dakplan en de werkdagen.")
    tectora_portal_show_report = fields.Boolean(
        string="Uitvoeringsverslag", default=True,
        help="Tab Uitvoeringsverslag: verslagen en foto's indienen.")
    tectora_portal_show_hours = fields.Boolean(
        string="Urenregistratie", default=True,
        help="De urenregistratie (start – stop / uren ingeven) en de uren op de werf.")

    tectora_hourly_cost = fields.Monetary(
        string="Uurkost",
        currency_field="currency_id",
        groups="project.group_project_manager,hr.group_hr_user",
        help="Wat een uur van deze persoon kost. De uren die hij op het "
        "portaal registreert, worden aan deze kost op het project geboekt "
        "(loonkost in de nacalculatie). Voor wie ook werknemer is, geldt de "
        "uurkost van de werknemersfiche: daar loopt het via de urenstaat.",
    )

    def _tectora_portal_segments(self):
        """``{segment: visible}`` of the site page for this person."""
        self.ensure_one()
        return {
            "overview": self.tectora_portal_show_overview,
            "materials": self.tectora_portal_show_materials,
            "plan": self.tectora_portal_show_plan,
            "report": self.tectora_portal_show_report,
            "hours": self.tectora_portal_show_hours,
        }

    def _tectora_portal_user(self):
        """The (active) login of this contact, a portal one first."""
        self.ensure_one()
        users = self.sudo().with_context(active_test=False).user_ids.filtered("active")
        return users.sorted(lambda user: not user.share)[:1]

    @api.depends("user_ids", "user_ids.share", "user_ids.active")
    def _compute_tectora_portal_access(self):
        for partner in self:
            user = partner._tectora_portal_user()
            if not user:
                partner.tectora_portal_state = "none"
            elif user.share:
                partner.tectora_portal_state = "portal"
            else:
                partner.tectora_portal_state = "internal"
            partner.tectora_portal_access = partner.tectora_portal_state == "portal"

    def _compute_tectora_is_worker(self):
        for partner in self:
            partner.tectora_is_worker = partner._tectora_is_worker()

    def _tectora_is_worker(self):
        """Works on the sites: in a ploeg, on a work block, or an employee."""
        self.ensure_one()
        if not self.id:
            return False
        if self.sudo().roof_team_ids or self._tectora_employees():
            return True
        Team = self.env["tectora.roof.team"].sudo()
        if Team.search_count([("leader_partner_id", "=", self.id)], limit=1):
            return True
        return bool(self.env["tectora.roof.planning"].sudo().search_count(
            [("partner_ids", "in", self.ids)], limit=1
        ))

    def _tectora_portal_horizon_end(self, moment=None):
        """UTC moment from which work blocks are hidden on this person's
        portal: the end of today plus a week or a month, counted from the
        start of the local day; None when the whole planning is shown."""
        self.ensure_one()
        horizon = self.tectora_portal_planning_horizon or "all"
        if horizon == "all":
            return None
        moment = moment or fields.Datetime.now()
        day_start, _day_end = self.env["tectora.roof.project"]._tectora_portal_day_bounds(moment)
        if horizon == "week":
            return day_start + relativedelta(days=7)
        return day_start + relativedelta(months=1)

    # ------------------------------------------------------------- portal user
    def action_tectora_grant_portal_access(self):
        """Give the contact a portal login and send the invitation."""
        group_portal = self.env.ref("base.group_portal")
        group_public = self.env.ref("base.group_public")
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        for partner in self:
            current = partner._tectora_portal_user()
            if current:
                if current.share:
                    raise UserError(
                        _("%s heeft al portaaltoegang (login %s).", partner.name, current.login)
                    )
                raise UserError(
                    _("%s is de interne gebruiker %s; die kan het portaal met "
                      "zijn gewone login gebruiken.", partner.name, current.login)
                )
            email = email_normalize(partner.email or "")
            if not email:
                raise UserError(
                    _("Vul eerst een e-mailadres in voor %s: dat wordt de login "
                      "van het portaal.", partner.name)
                )
            company = partner.company_id or self.env.company
            # A login that was archived comes back.
            user = partner.sudo().with_context(active_test=False).user_ids[:1]
            if not user:
                user = Users.search([("login", "=", email)], limit=1)
                if user and not user.share and user.active:
                    raise UserError(
                        _("Het e-mailadres %s is al de login van een interne "
                          "gebruiker.", email)
                    )
                if user and user.partner_id != partner:
                    raise UserError(
                        _("Er bestaat al een gebruiker met login %s voor een "
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
                    # the site works in the person's timezone and language
                    "tz": partner.tz or company.partner_id.tz or user.tz,
                    "lang": company.partner_id.lang or self.env.user.lang or user.lang,
                }
            )
            partner._tectora_send_portal_invitation(user)
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
                    "Welkom op het portaal van %s. Na het instellen van je "
                    "wachtwoord vind je je werven onder Mijn werven.",
                    (self.company_id or self.env.company).name,
                ),
            ).send_mail(user.id, force_send=True)
        except Exception:  # pragma: no cover - mail server issues
            _logger.exception("Could not send the portal invitation to %s", user.login)
            return False
        return True

    def action_tectora_open_portal_user(self):
        self.ensure_one()
        user = self._tectora_portal_user()
        if not user:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.users",
            "res_id": user.id,
            "view_mode": "form",
            "target": "current",
        }
