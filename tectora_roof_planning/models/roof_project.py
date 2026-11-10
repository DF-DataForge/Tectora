# -*- coding: utf-8 -*-
from odoo import _, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    def action_view_planning(self):
        """With the Planning app the work blocks open in the team planner,
        the whole planning (every team, every project) to plan this project
        among the others: a new block is this project's, and "Beschikbare
        momenten" shows the teams' free periods for it."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "tectora_roof_planning.action_tectora_roof_planning_by_team"
        )
        action["name"] = _("Planning — %s") % self.display_name
        action["context"] = {
            "default_project_id": self.id,
            "default_team_id": self.team_id.id,
            "default_start_datetime": self.planned_date_begin,
            "default_end_datetime": self.planned_date_end,
            "tectora_project_id": self.id,
            "initial_date": fields.Date.to_string(
                (self.planned_date_begin or fields.Datetime.now()).date()
            ),
        }
        return self.env["tectora.roof.planning"]._drop_unavailable_views(action)
