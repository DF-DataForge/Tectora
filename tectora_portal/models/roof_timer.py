# -*- coding: utf-8 -*-
"""Start/stop hour registration on a site.

One timer runs per roof project. Whoever presses Start on the portal opens
it; whoever presses Stop closes it and confirms the crew that was present --
proposed from the planner: the persons on the work block(s) of that day.

The registration runs on contacts: the crew are contacts, an employee record
is not needed. For whoever is an employee too (the contact is their work
contact) stopping writes a timesheet line on the project, so those hours and
their labour cost land in the post-calculation like any other timesheet; the
hours of the others stay on the registration.
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.tectora_roof.models.project_task import WORK_KINDS

_logger = logging.getLogger(__name__)


class TectoraRoofTimer(models.Model):
    _name = "tectora.roof.timer"
    _description = "Urenregistratie werf"
    _order = "start_datetime desc, id desc"

    name = fields.Char(string="Registratie", compute="_compute_name", store=True)
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    dossier_project_id = fields.Many2one(
        related="project_id.project_id", string="Project", store=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    partner_id = fields.Many2one(related="project_id.partner_id", string="Klant")
    address = fields.Char(related="project_id.address", string="Werfadres")
    planning_id = fields.Many2one(
        "tectora.roof.planning",
        string="Werkblok",
        ondelete="set null",
        help="Het werkblok van die dag waaruit de aanwezige ploeg voorgesteld werd.",
    )
    work_kind = fields.Selection(
        WORK_KINDS,
        string="Werksoort",
        default="uitvoering",
        required=True,
        index=True,
        help="Waaraan gewerkt werd: de uren komen op de taak Afbraakwerken of "
        "Uitvoeringswerken van het project, zodat afbraak en uitvoering in "
        "de urenstaten uit elkaar te houden zijn.",
    )
    scope = fields.Selection(
        [("team", "Ploeg"), ("individual", "Individueel")],
        string="Voor",
        default="team",
        required=True,
        index=True,
        help="Ploeg: de ploegleider logt voor de aanwezige ploeg. Individueel: "
        "een medewerker logt enkel zijn eigen uren.",
    )
    entry_mode = fields.Selection(
        [("timer", "Start – stop"), ("manual", "Rechtstreeks ingegeven")],
        string="Manier",
        default="timer",
        required=True,
    )
    start_datetime = fields.Datetime(
        string="Start", required=True, default=fields.Datetime.now, index=True
    )
    end_datetime = fields.Datetime(string="Stop")
    duration_hours = fields.Float(
        string="Duur (uren)", compute="_compute_duration_hours", store=True,
        help="Uren tussen start en stop; van een lopende registratie: tot nu.",
    )
    state = fields.Selection(
        [
            ("running", "Lopend"),
            ("done", "Gestopt"),
            ("cancelled", "Geannuleerd"),
        ],
        string="Status",
        default="running",
        required=True,
        index=True,
    )
    started_by_partner_id = fields.Many2one(
        "res.partner", string="Gestart door", ondelete="set null"
    )
    stopped_by_partner_id = fields.Many2one(
        "res.partner", string="Gestopt door", ondelete="set null"
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "tectora_roof_timer_partner_rel",
        "timer_id",
        "partner_id",
        string="Aanwezige personen",
        help="De personen (contacten) voor wie de uren geregistreerd worden: "
        "de ploeg van het werkblok van die dag, bevestigd bij het stoppen.",
    )
    partner_count = fields.Integer(compute="_compute_employee_count")
    started_by_id = fields.Many2one(
        "hr.employee", string="Gestart door (werknemer)",
        compute="_compute_by_employee",
    )
    stopped_by_id = fields.Many2one(
        "hr.employee", string="Gestopt door (werknemer)",
        compute="_compute_by_employee",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "tectora_roof_timer_employee_rel",
        "timer_id",
        "employee_id",
        string="Werknemers",
        compute="_compute_employee_ids",
        inverse="_inverse_employee_ids",
        store=True,
        readonly=False,
        help="De werknemers achter de aanwezige personen: voor hen wordt een "
        "urenstaatlijn geboekt.",
    )
    employee_count = fields.Integer(compute="_compute_employee_count")
    registered_hours = fields.Float(
        string="Geregistreerde uren",
        compute="_compute_registered_hours",
        help="Uren van alle aanwezige personen samen: de urenstaatlijnen van "
        "de werknemers plus de duur voor elke persoon zonder werknemersfiche.",
    )
    contact_hours = fields.Float(
        string="Uren zonder urenstaat",
        compute="_compute_registered_hours",
        help="Uren van de aanwezige personen die geen werknemer zijn: daar "
        "wordt geen urenstaatlijn voor geboekt.",
    )
    timesheet_ids = fields.One2many(
        "account.analytic.line", "tectora_timer_id", string="Urenstaatlijnen"
    )
    timesheet_count = fields.Integer(compute="_compute_timesheet_count")
    timesheet_hours = fields.Float(
        string="Geboekte uren", compute="_compute_timesheet_count",
        help="Som van de uren op de urenstaatlijnen (alle medewerkers samen).",
    )
    notes = fields.Text(string="Werknota")

    @api.constrains("start_datetime", "end_datetime")
    def _check_dates(self):
        for timer in self:
            if timer.end_datetime and timer.end_datetime < timer.start_datetime:
                raise ValidationError(_("De stoptijd kan niet voor de starttijd liggen."))

    @api.depends("project_id.code", "project_id.name", "start_datetime")
    def _compute_name(self):
        for timer in self:
            project = timer.project_id
            reference = project.code or project.name or ""
            when = ""
            if timer.start_datetime:
                when = fields.Datetime.context_timestamp(
                    timer, timer.start_datetime
                ).strftime("%d/%m/%Y %H:%M")
            timer.name = " — ".join(filter(None, ["Uren", reference, when]))

    @api.depends("start_datetime", "end_datetime", "state")
    def _compute_duration_hours(self):
        now = fields.Datetime.now()
        for timer in self:
            if not timer.start_datetime or timer.state == "cancelled":
                timer.duration_hours = 0.0
                continue
            end = timer.end_datetime or now
            timer.duration_hours = max(
                (end - timer.start_datetime).total_seconds() / 3600.0, 0.0
            )

    @api.depends("partner_ids", "employee_ids")
    def _compute_employee_count(self):
        for timer in self:
            timer.partner_count = len(timer.partner_ids)
            timer.employee_count = len(timer.employee_ids)

    @api.depends("partner_ids")
    def _compute_employee_ids(self):
        """The employees behind the persons present."""
        for timer in self:
            timer.employee_ids = timer.partner_ids._tectora_employees()

    def _inverse_employee_ids(self):
        """Employees set on a registration (older code, the back office):
        their work contacts are the persons present."""
        for timer in self:
            employees = timer.sudo().employee_ids
            for employee in employees.filtered(lambda e: not e.work_contact_id):
                employee._create_work_contacts()
            behind = timer.partner_ids._tectora_employees()
            partners = (timer.partner_ids - behind.work_contact_id) | employees.work_contact_id
            if partners != timer.partner_ids:
                timer.partner_ids = partners

    @api.depends("started_by_partner_id", "stopped_by_partner_id")
    def _compute_by_employee(self):
        for timer in self:
            timer.started_by_id = timer.started_by_partner_id._tectora_employees()[:1]
            timer.stopped_by_id = timer.stopped_by_partner_id._tectora_employees()[:1]

    @api.depends(
        "partner_ids", "employee_ids", "duration_hours", "state",
        "timesheet_ids.unit_amount",
    )
    def _compute_registered_hours(self):
        for timer in self:
            if timer.state != "done":
                timer.contact_hours = 0.0
                timer.registered_hours = 0.0
                continue
            with_sheet = timer.sudo().timesheet_ids.employee_id.work_contact_id
            if not timer.timesheet_ids:
                # nothing booked (yet): everyone counts for the duration
                with_sheet = self.env["res.partner"]
            others = timer.partner_ids - with_sheet
            timer.contact_hours = round(timer.duration_hours, 2) * len(others)
            timer.registered_hours = (
                sum(timer.timesheet_ids.mapped("unit_amount")) + timer.contact_hours
            )

    @api.depends("timesheet_ids.unit_amount")
    def _compute_timesheet_count(self):
        for timer in self:
            timer.timesheet_count = len(timer.timesheet_ids)
            timer.timesheet_hours = sum(timer.timesheet_ids.mapped("unit_amount"))

    # ------------------------------------------------------------------ helpers
    def _tz(self):
        """Timezone the site works in: the user's, else the company's, else
        Belgium (the sites are)."""
        name = (
            self.env.user.tz
            or (self.company_id or self.env.company).partner_id.tz
            or "Europe/Brussels"
        )
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:  # pragma: no cover
            return pytz.timezone("Europe/Brussels")

    def _local(self, value):
        self.ensure_one()
        return pytz.utc.localize(value).astimezone(self._tz())

    def _elapsed_hours(self):
        """Hours between start and stop, until now while running -- computed
        live, the stored ``duration_hours`` of a running timer being the value
        at its last write."""
        self.ensure_one()
        if not self.start_datetime or self.state == "cancelled":
            return 0.0
        end = self.end_datetime or fields.Datetime.now()
        return max((end - self.start_datetime).total_seconds() / 3600.0, 0.0)

    def _work_kind_label(self):
        """``Afbraakwerken`` / ``Uitvoeringswerken``, for the portal."""
        self.ensure_one()
        return dict(WORK_KINDS).get(self.work_kind, "")

    def _elapsed_display(self):
        """``H:MM`` of the registration (until now when still running)."""
        self.ensure_one()
        minutes = int(round(self._elapsed_hours() * 60))
        return "%d:%02d" % (minutes // 60, minutes % 60)

    @api.model
    def _running_for(self, project, scope="team", partner=None):
        """The running registration of a site: the team one, or the
        individual one of ``partner``."""
        domain = [
            ("project_id", "=", project.id), ("state", "=", "running"),
            ("scope", "=", scope),
        ]
        if scope == "individual":
            domain.append(("partner_ids", "in", partner.ids if partner else []))
        return self.search(domain, order="start_datetime asc", limit=1)

    @api.model
    def _work_kind_value(self, work_kind):
        return work_kind if work_kind in dict(WORK_KINDS) else "uitvoering"

    # ------------------------------------------------------------------- start
    @api.model
    def _start(self, project, partner, notes=None, work_kind=None, scope="team"):
        """Open a timer of a site from the portal: the team one (one per
        site) or ``partner``'s own one (one per person and site).

        :param work_kind: ``afbraak`` or ``uitvoering``, the task the hours
            will be booked on; execution when not given.
        """
        scope = "individual" if scope == "individual" else "team"
        running = self._running_for(project, scope, partner)
        if running:
            if scope == "individual":
                raise UserError(_("Je urenregistratie op %s loopt al.", project.display_name))
            raise UserError(
                _("Er loopt al een urenregistratie op %s (gestart door %s).",
                  project.display_name,
                  running.started_by_partner_id.name or _("onbekend"))
            )
        now = fields.Datetime.now()
        block = project._tectora_portal_block_at(now)
        if scope == "individual":
            team_timer = self._running_for(project, "team")
            if partner and partner in team_timer.partner_ids:
                raise UserError(_(
                    "Je telt mee in de lopende ploegregistratie (gestart door %s); "
                    "je uren worden daar al geboekt.",
                    team_timer.started_by_partner_id.name or _("onbekend")))
            partners = partner
        else:
            partners = project._tectora_portal_planned_partners(now)
            if partner and partner not in partners:
                partners |= partner
        return self.create(
            {
                "project_id": project.id,
                "planning_id": block.id if block else False,
                "start_datetime": now,
                "started_by_partner_id": partner.id if partner else False,
                "partner_ids": [(6, 0, partners.ids)],
                "notes": notes or False,
                "work_kind": self._work_kind_value(work_kind),
                "scope": scope,
            }
        )

    @api.model
    def _log_manual(self, project, partner, date, hours, partners=None,
                    work_kind=None, notes=None, scope="team"):
        """Hours entered directly on the portal: a closed registration of
        ``hours`` on ``date`` (from 8:00 local), booked at once for
        ``partners`` (individually: only ``partner``)."""
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            raise UserError(_("Geef een geldig aantal uren in."))
        if hours <= 0 or hours > 24:
            raise UserError(_("Het aantal uren moet tussen 0 en 24 liggen."))
        date = fields.Date.to_date(date) or fields.Date.context_today(self)
        if date > fields.Date.context_today(self):
            raise UserError(_("Uren kunnen niet voor een dag in de toekomst ingegeven worden."))
        scope = "individual" if scope == "individual" else "team"
        if scope == "individual" or not partners:
            partners = partner
        if not partners:
            raise UserError(_("Kies minstens één persoon voor wie de uren geboekt worden."))
        tz = self._tz()
        start = tz.localize(datetime.combine(date, time(8, 0))).astimezone(pytz.utc)
        start = start.replace(tzinfo=None)
        end = start + timedelta(hours=hours)
        block = project._tectora_portal_block_at(start)
        timer = self.create(
            {
                "project_id": project.id,
                "planning_id": block.id if block else False,
                "start_datetime": start,
                "end_datetime": end,
                "state": "done",
                "started_by_partner_id": partner.id if partner else False,
                "stopped_by_partner_id": partner.id if partner else False,
                "partner_ids": [(6, 0, partners.ids)],
                "notes": notes or False,
                "work_kind": self._work_kind_value(work_kind),
                "scope": scope,
                "entry_mode": "manual",
            }
        )
        timer._create_timesheets()
        return timer

    # -------------------------------------------------------------------- stop
    def action_stop(self, partner_ids=None, stopped_by=None, notes=None, end=None):
        """Close the timer and book the hours for the confirmed crew.

        :param partner_ids: the persons (contacts) that were present;
            ``None`` keeps the planned crew stored at start.
        :param stopped_by: the contact that stops it.
        """
        end = end or fields.Datetime.now()
        for timer in self:
            if timer.state != "running":
                raise UserError(_("Deze urenregistratie loopt niet meer."))
            values = {
                "end_datetime": max(end, timer.start_datetime),
                "state": "done",
            }
            if stopped_by:
                values["stopped_by_partner_id"] = stopped_by.id
            if notes:
                values["notes"] = "\n".join(filter(None, [timer.notes, notes]))
            if partner_ids is not None:
                values["partner_ids"] = [(6, 0, list(partner_ids))]
            timer.write(values)
            timer._create_timesheets()
        return True

    def action_cancel(self):
        for timer in self:
            timer.timesheet_ids.sudo().unlink()
            timer.write({"state": "cancelled", "end_datetime": timer.end_datetime or fields.Datetime.now()})
        return True

    def action_open_roof_project(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": self.project_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_timesheets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Urenstaatlijnen"),
            "res_model": "account.analytic.line",
            "view_mode": "list,form",
            "domain": [("tectora_timer_id", "=", self.id)],
            "context": {"default_tectora_timer_id": self.id},
        }

    # -------------------------------------------------------------- timesheets
    def _timesheet_description(self):
        self.ensure_one()
        start = self._local(self.start_datetime)
        end = self._local(self.end_datetime or fields.Datetime.now())
        parts = [
            _("Werf %s", self.project_id.display_name),
            dict(WORK_KINDS).get(self.work_kind, ""),
            _("%s u ingegeven", self._elapsed_display())
            if self.entry_mode == "manual"
            else "%s–%s" % (start.strftime("%H:%M"), end.strftime("%H:%M")),
        ]
        if self.notes:
            parts.append(self.notes.strip())
        return " · ".join(parts)

    def _timesheet_unit_amount(self, company):
        """The registration's hours in the company's timesheet unit."""
        self.ensure_one()
        hours = round(self.duration_hours, 2)
        hour_uom = self.env.ref("uom.product_uom_hour", raise_if_not_found=False)
        encoding = company.project_time_mode_id
        if hour_uom and encoding and encoding != hour_uom:
            return hour_uom._compute_quantity(hours, encoding, raise_if_failure=False)
        return hours

    def _create_timesheets(self):
        """One timesheet line per present person that is an employee, on
        the project dossier (created if the order was not confirmed yet). A
        timesheet needs an employee: the hours of the others stay on the
        registration (``contact_hours``)."""
        for timer in self:
            if timer.timesheet_ids or timer.state != "done":
                continue
            if timer.duration_hours * 60 < 1:
                continue
            employees = timer.employee_ids.filtered("active")
            if not employees:
                continue
            roof_project = timer.project_id.sudo()
            dossier = roof_project._ensure_project()
            if not dossier:
                _logger.warning(
                    "No project to book the hours of %s on", timer.display_name
                )
                continue
            if not dossier.allow_timesheets:
                dossier.write({"allow_timesheets": True})
            # The task of the work kind: Afbraakwerken or Uitvoeringswerken,
            # created here if the order's confirmation did not make it yet.
            task = dossier._tectora_work_task(timer.work_kind, create=True)
            date = timer._local(timer.start_datetime).date()
            description = timer._timesheet_description()
            vals_list = []
            company_ids = set()
            for employee in employees:
                company = employee.company_id or dossier.company_id or self.env.company
                company_ids.add(company.id)
                vals_list.append(
                    {
                        "name": description,
                        "project_id": dossier.id,
                        "task_id": task.id,
                        "employee_id": employee.id,
                        "date": date,
                        "unit_amount": timer._timesheet_unit_amount(company),
                        "company_id": company.id,
                        "tectora_timer_id": timer.id,
                    }
                )
            Line = self.env["account.analytic.line"].sudo().with_context(
                allowed_company_ids=list(company_ids | {dossier.company_id.id}),
                tectora_sync=True,
            )
            Line.create(vals_list)
        return True

    # ------------------------------------------------------------------ cleanup
    @api.model
    def _cron_stop_forgotten_timers(self, max_hours=16):
        """A timer nobody stopped is closed at the end of its day (well, after
        ``max_hours``) so it does not book a week of hours by accident. The
        hours are still written; the back office can correct the lines."""
        limit = fields.Datetime.now() - timedelta(hours=max_hours)
        forgotten = self.search(
            [("state", "=", "running"), ("start_datetime", "<=", limit)]
        )
        for timer in forgotten:
            end = timer.start_datetime + timedelta(hours=max_hours)
            timer.action_stop(
                end=end,
                notes=_("Automatisch gestopt na %s uur (niet gestopt op het portaal).", max_hours),
            )
        return True
