# -*- coding: utf-8 -*-
from odoo import _, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    def action_view_planning(self):
        """The work blocks open in the project planner, the whole planning
        (every team, every project) to plan this project among the others: a
        new block is this project's, a click on free cells plans it there at
        once, and "Beschikbare momenten" shows the teams' free periods for
        it."""
        self.ensure_one()
        Planning = self.env["tectora.roof.planning"]
        action = Planning._tectora_planner_action()
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
        return action
