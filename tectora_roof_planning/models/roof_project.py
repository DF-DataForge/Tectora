# -*- coding: utf-8 -*-
from odoo import models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    def action_view_planning(self):
        """With the Planning app the work blocks open in the team planner:
        one project block per ploeg, the shifts follow the block."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "tectora_roof_planning.action_tectora_roof_planning_by_team"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "default_project_id": self.id,
            "default_team_id": self.team_id.id,
            "default_start_datetime": self.planned_date_begin,
            "default_end_datetime": self.planned_date_end,
        }
        return self.env["tectora.roof.planning"]._drop_unavailable_views(action)
