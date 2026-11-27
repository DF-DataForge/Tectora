# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class TectoraRoofPlanning(models.Model):
    """What the crew did on the portal for a work block: the hours they
    registered with the start/stop timer and their execution reports, on the
    block in the planner."""

    _inherit = "tectora.roof.planning"

    timer_ids = fields.One2many(
        "tectora.roof.timer", "planning_id", string="Urenregistraties (portaal)"
    )
    execution_report_ids = fields.One2many(
        "tectora.roof.execution.report", "planning_id", string="Uitvoeringsverslagen"
    )
    portal_hours = fields.Float(
        string="Geregistreerde uren",
        compute="_compute_portal_totals",
        help="Uren die de ploeg voor dit werkblok op het portaal registreerde "
        "(start/stop of ingegeven), alle personen samen.",
    )
    portal_running = fields.Boolean(
        string="Registratie loopt", compute="_compute_portal_totals",
        help="Er loopt nu een urenregistratie op dit werkblok.",
    )
    execution_report_count = fields.Integer(
        string="Verslagen", compute="_compute_portal_totals"
    )

    @api.depends("timer_ids.registered_hours", "timer_ids.state", "execution_report_ids")
    def _compute_portal_totals(self):
        for block in self:
            timers = block.timer_ids
            block.portal_hours = sum(
                timers.filtered(lambda timer: timer.state == "done").mapped("registered_hours")
            )
            block.portal_running = any(timer.state == "running" for timer in timers)
            block.execution_report_count = len(block.execution_report_ids)

    def action_view_portal_timers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Urenregistraties"),
            "res_model": "tectora.roof.timer",
            "view_mode": "list,form",
            "domain": [("planning_id", "=", self.id)],
            "context": {
                "default_project_id": self.project_id.id,
                "default_planning_id": self.id,
            },
        }

    def action_view_portal_reports(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Uitvoeringsverslagen"),
            "res_model": "tectora.roof.execution.report",
            "view_mode": "list,form",
            "domain": [("planning_id", "=", self.id)],
            "context": {
                "default_project_id": self.project_id.id,
                "default_planning_id": self.id,
            },
        }
