# -*- coding: utf-8 -*-
"""Start/stop hour registration on a site.

One timer runs per roof project. Whoever presses Start on the portal opens
it; whoever presses Stop closes it and confirms the crew that was present --
proposed from the planner: the employees on the work block(s) of that day.
Stopping writes one timesheet line per employee on the project, so the hours
and the labour cost land in the post-calculation like any other timesheet.
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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
    started_by_id = fields.Many2one(
        "hr.employee", string="Gestart door", ondelete="set null"
    )
    stopped_by_id = fields.Many2one(
        "hr.employee", string="Gestopt door", ondelete="set null"
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "tectora_roof_timer_employee_rel",
        "timer_id",
        "employee_id",
        string="Aanwezige medewerkers",
        help="De medewerkers voor wie de uren geboekt worden: de ploeg van het "
        "werkblok van die dag, bevestigd bij het stoppen.",
    )
    employee_count = fields.Integer(compute="_compute_employee_count")
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

    def _compute_employee_count(self):
        for timer in self:
            timer.employee_count = len(timer.employee_ids)

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

    def _elapsed_display(self):
        """``H:MM`` of the registration (until now when still running)."""
        self.ensure_one()
        minutes = int(round(self._elapsed_hours() * 60))
        return "%d:%02d" % (minutes // 60, minutes % 60)

    @api.model
    def _running_for(self, project):
        return self.search(
            [("project_id", "=", project.id), ("state", "=", "running")],
            order="start_datetime asc",
            limit=1,
        )

    # ------------------------------------------------------------------- start
    @api.model
    def _start(self, project, employee, notes=None):
        """Open the timer of a site from the portal. Refuses a second one."""
        running = self._running_for(project)
        if running:
            raise UserError(
                _("Er loopt al een urenregistratie op %s (gestart door %s).",
                  project.display_name,
                  running.started_by_id.name or _("onbekend"))
            )
        now = fields.Datetime.now()
        block = project._tectora_portal_block_at(now)
        employees = project._tectora_portal_planned_employees(now)
        if employee and employee not in employees:
            employees |= employee
        return self.create(
            {
                "project_id": project.id,
                "planning_id": block.id if block else False,
                "start_datetime": now,
                "started_by_id": employee.id if employee else False,
                "employee_ids": [(6, 0, employees.ids)],
                "notes": notes or False,
            }
        )

    # -------------------------------------------------------------------- stop
    def action_stop(self, employee_ids=None, stopped_by=None, notes=None, end=None):
        """Close the timer and book the hours for the confirmed crew.

        :param employee_ids: the employees that were present; ``None`` keeps
            the planned crew stored at start.
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
                values["stopped_by_id"] = stopped_by.id
            if notes:
                values["notes"] = "\n".join(filter(None, [timer.notes, notes]))
            if employee_ids is not None:
                values["employee_ids"] = [(6, 0, list(employee_ids))]
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
            "%s–%s" % (start.strftime("%H:%M"), end.strftime("%H:%M")),
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
        """One timesheet line per present employee on the project dossier
        (created if the order was not confirmed yet)."""
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
