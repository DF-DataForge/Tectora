# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectProject(models.Model):
    """The project dashboard shows the employees' shifts of the Planning app
    and opens the resource planner instead of the work blocks."""

    _inherit = "project.project"

    tectora_slot_ids = fields.Many2many(
        "planning.slot",
        string="Planning-items",
        compute="_compute_tectora_slots",
        help="Shifts van de medewerkers op het dakproject van dit project.",
    )
    tectora_slot_count = fields.Integer(compute="_compute_tectora_slots")

    @api.depends("roof_project_id")
    def _compute_tectora_slots(self):
        Slot = self.env["planning.slot"]
        for project in self:
            roof = project.roof_project_id
            slots = Slot
            if roof and roof.id:
                slots = Slot.search(
                    [("roof_project_id", "=", roof.id)], order="start_datetime, id"
                )
            project.tectora_slot_ids = slots
            project.tectora_slot_count = len(slots)

    def action_view_tectora_planning(self):
        """This project's blocks in the team planner (one project block per
        ploeg; the individual shifts are a click further)."""
        self.ensure_one()
        roof = self._tectora_ensure_roof_project()
        if not roof:
            return super().action_view_tectora_planning()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "tectora_roof_planning.action_tectora_roof_planning_by_team"
        )
        action["domain"] = [("project_id", "=", roof.id)]
        action["context"] = {
            "default_project_id": roof.id,
            "default_team_id": roof.team_id.id,
            "default_start_datetime": roof.planned_date_begin,
            "default_end_datetime": roof.planned_date_end,
        }
        return self.env["tectora.roof.planning"]._drop_unavailable_views(action)
