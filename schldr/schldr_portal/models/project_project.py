# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    """The portal's reports and hour registrations, mirrored on the project
    dashboard's Uitvoering tab."""

    _inherit = "project.project"

    schldr_execution_report_ids = fields.One2many(
        related="schldr_project_id.execution_report_ids", string="Uitvoeringsverslagen"
    )
    schldr_timer_ids = fields.One2many(
        related="schldr_project_id.timer_ids", string="Urenregistraties"
    )
    schldr_running_timer_id = fields.Many2one(
        related="schldr_project_id.running_timer_id", string="Lopende registratie"
    )
    schldr_portal_hours = fields.Float(
        related="schldr_project_id.portal_hours", string="Uren (portaal)"
    )
    schldr_execution_report_count = fields.Integer(
        related="schldr_project_id.execution_report_count", string="Verslagen"
    )

    def action_view_schldr_execution_reports(self):
        self.ensure_one()
        if not self.schldr_project_id:
            return False
        return self.schldr_project_id.action_view_execution_reports()

    def action_view_schldr_timers(self):
        self.ensure_one()
        if not self.schldr_project_id:
            return False
        return self.schldr_project_id.action_view_timers()
