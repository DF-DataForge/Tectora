# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    timer_ids = fields.One2many(
        "tectora.roof.timer", "project_id", string="Urenregistraties"
    )
    running_timer_id = fields.Many2one(
        "tectora.roof.timer", string="Lopende registratie",
        compute="_compute_running_timer_id",
    )
    timer_count = fields.Integer(compute="_compute_portal_totals")
    portal_hours = fields.Float(
        string="Geregistreerde uren", compute="_compute_portal_totals",
        help="Uren geboekt via de start/stop-registratie op het portaal, "
        "alle medewerkers samen.",
    )
    execution_report_ids = fields.One2many(
        "tectora.roof.execution.report", "project_id", string="Uitvoeringsverslagen"
    )
    execution_report_count = fields.Integer(compute="_compute_portal_totals")

    @api.depends("timer_ids.state")
    def _compute_running_timer_id(self):
        for project in self:
            project.running_timer_id = project.timer_ids.filtered(
                lambda timer: timer.state == "running"
            ).sorted("start_datetime")[:1]

    @api.depends("timer_ids.timesheet_hours", "timer_ids.state", "execution_report_ids")
    def _compute_portal_totals(self):
        for project in self:
            done = project.timer_ids.filtered(lambda timer: timer.state == "done")
            project.timer_count = len(project.timer_ids)
            project.portal_hours = sum(done.mapped("timesheet_hours"))
            project.execution_report_count = len(project.execution_report_ids)

    # ----------------------------------------------------------------- portal
    @api.model
    def _tectora_portal_domain(self, employee):
        """The sites an employee sees on the portal: every roof project they
        are planned on (a work block with them on it), plus -- for a ploeg
        member or ploegbaas -- the projects assigned to their team."""
        if not employee:
            return [("id", "=", False)]
        return [
            "|",
            ("planning_ids", "any", [("employee_ids", "in", employee.ids)]),
            "|",
            ("team_id.employee_ids", "in", employee.ids),
            ("team_id.leader_id", "in", employee.ids),
        ]

    @api.model
    def _tectora_portal_day_bounds(self, moment, tz=None):
        """UTC bounds of the local calendar day ``moment`` falls in."""
        tz = tz or pytz.timezone(
            self.env.user.tz or self.env.company.partner_id.tz or "Europe/Brussels"
        )
        local = pytz.utc.localize(moment).astimezone(tz)
        day_start = tz.localize(datetime.combine(local.date(), time.min))
        day_end = day_start + timedelta(days=1)
        return (
            day_start.astimezone(pytz.utc).replace(tzinfo=None),
            day_end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _tectora_portal_blocks_at(self, moment):
        """The work blocks of this project that touch the day of ``moment``."""
        self.ensure_one()
        start, end = self._tectora_portal_day_bounds(moment)
        return self.planning_ids.filtered(
            lambda block: block.start_datetime and block.end_datetime
            and block.start_datetime < end and block.end_datetime > start
        ).sorted("start_datetime")

    def _tectora_portal_block_at(self, moment):
        self.ensure_one()
        return self._tectora_portal_blocks_at(moment)[:1]

    def _tectora_portal_planned_employees(self, moment):
        """Who is planned on the site at ``moment``, as per the planner: the
        employees of that day's work block(s). Without a block that day, the
        employees of the closest block; without any block, the team."""
        self.ensure_one()
        blocks = self._tectora_portal_blocks_at(moment)
        if not blocks:
            candidates = self.planning_ids.filtered("start_datetime")
            if candidates:
                blocks = candidates.sorted(
                    key=lambda block: abs((block.start_datetime - moment).total_seconds())
                )[:1]
        employees = blocks.employee_ids
        if not employees and self.team_id:
            employees = self.team_id.member_ids
        return employees.filtered("active")

    def _tectora_portal_next_block(self, moment=None):
        self.ensure_one()
        moment = moment or fields.Datetime.now()
        upcoming = self.planning_ids.filtered(
            lambda block: block.end_datetime and block.end_datetime >= moment
        ).sorted("start_datetime")
        return upcoming[:1]

    def _tectora_portal_planned_employee_ids(self):
        self.ensure_one()
        return (self.planning_ids.employee_ids | self.team_id.member_ids).filtered("active")

    # ---------------------------------------------------------------- buttons
    def action_view_timers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Urenregistraties",
            "res_model": "tectora.roof.timer",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_execution_reports(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Uitvoeringsverslagen",
            "res_model": "tectora.roof.execution.report",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }
