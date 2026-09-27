# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    """The portal's reports and hour registrations, mirrored on the project
    dashboard's Uitvoering tab."""

    _inherit = "project.project"

    roof_execution_report_ids = fields.One2many(
        related="roof_project_id.execution_report_ids", string="Uitvoeringsverslagen"
    )
    roof_timer_ids = fields.One2many(
        related="roof_project_id.timer_ids", string="Urenregistraties"
    )
    roof_running_timer_id = fields.Many2one(
        related="roof_project_id.running_timer_id", string="Lopende registratie"
    )
    roof_portal_hours = fields.Float(
        related="roof_project_id.portal_hours", string="Uren (portaal)"
    )
    roof_execution_report_count = fields.Integer(
        related="roof_project_id.execution_report_count", string="Verslagen"
    )

    def action_view_roof_execution_reports(self):
        self.ensure_one()
        if not self.roof_project_id:
            return False
        return self.roof_project_id.action_view_execution_reports()

    def action_view_roof_timers(self):
        self.ensure_one()
        if not self.roof_project_id:
            return False
        return self.roof_project_id.action_view_timers()
