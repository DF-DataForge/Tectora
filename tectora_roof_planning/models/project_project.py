# -*- coding: utf-8 -*-
from odoo import api, models


class ProjectProject(models.Model):
    """The project dashboard counts the planned hours as the planner does:
    working hours (8 per working day and per employee), not the hours
    between a block's start and end."""

    _inherit = "project.project"

    # An overriding compute replaces the dependencies: the base ones too.
    @api.depends(
        "roof_project_id.planning_ids.start_datetime",
        "roof_project_id.planning_ids.end_datetime",
        "roof_project_id.planning_ids.employee_ids",
        "roof_project_id.planning_ids.state",
        "roof_project_id.planning_ids.planned_hours",
    )
    def _compute_tectora_planning(self):
        super()._compute_tectora_planning()
        for project in self:
            project.tectora_planning_hours = sum(
                project.roof_project_id.planning_ids.mapped("planned_hours")
            )
