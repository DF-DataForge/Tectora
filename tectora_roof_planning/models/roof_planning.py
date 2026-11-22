# -*- coding: utf-8 -*-
"""The project planner: the work blocks as the planning itself.

A work block (``tectora.roof.planning``) is planned on a project, for a team
and its employees. The planner of the Project app shows the blocks per
ploeg, per medewerker and per project; no shifts of the Planning app are
made for them any more. What that app gave on top is done on the blocks
themselves: the planning per employee (a block is on the row of each of its
employees), who is planned twice at the same time, and the hours planned.
"""
import logging

from datetime import timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

TEAM_PLANNER_XMLID = "tectora_roof_planning.action_tectora_roof_planning_by_team"
EMPLOYEE_PLANNER_XMLID = "tectora_roof_planning.action_tectora_roof_planning_by_employee"
# A working day on the planner counts 8 hours per person.
HOURS_PER_DAY = 8.0


class TectoraRoofPlanning(models.Model):
    _inherit = "tectora.roof.planning"

    planned_hours = fields.Float(
        string="Geplande uren",
        compute="_compute_planned_hours",
        store=True,
        help="De werkuren van het blok (8 uur per werkdag, maandag tot "
        "vrijdag; een blok binnen één dag zijn eigen duur) maal het aantal "
        "medewerkers erop.",
    )
    conflict_employee_ids = fields.Many2many(
        "hr.employee",
        string="Dubbel ingepland",
        compute="_compute_conflicts",
        help="Medewerkers van dit blok die in dezelfde periode ook op een "
        "ander werkblok staan.",
    )
    conflict_planning_ids = fields.Many2many(
        "tectora.roof.planning",
        string="Overlappende werkblokken",
        compute="_compute_conflicts",
    )
    has_conflict = fields.Boolean(
        string="Dubbel ingepland?",
        compute="_compute_conflicts",
        search="_search_has_conflict",
    )

    # ------------------------------------------------------------ hours
    @api.depends("start_datetime", "end_datetime", "employee_ids")
    def _compute_planned_hours(self):
        for item in self:
            item.planned_hours = item._tectora_working_day_hours() * max(
                len(item.employee_ids), 1
            )

    def _tectora_working_day_hours(self):
        """The working hours the block covers for one person."""
        self.ensure_one()
        if not (self.start_datetime and self.end_datetime):
            return 0.0
        tz = self._tectora_tz()
        start = pytz.utc.localize(self.start_datetime).astimezone(tz)
        end = pytz.utc.localize(self.end_datetime).astimezone(tz)
        if end <= start:
            return 0.0
        if start.date() == end.date():
            return min((end - start).total_seconds() / 3600.0, HOURS_PER_DAY)
        days = 0
        day = start.date()
        while day <= end.date():
            if day.weekday() < 5:
                days += 1
            day += timedelta(days=1)
        return days * HOURS_PER_DAY

    # -------------------------------------------------------- conflicts
    def _tectora_overlapping(self):
        """The other blocks in this block's period that share an employee
        with it (blocks already carried out leave the planner alone)."""
        self.ensure_one()
        if not (self.employee_ids and self.start_datetime and self.end_datetime):
            return self.browse()
        if self.state == "done":
            return self.browse()
        # .ids / _origin: also right while the block is being edited.
        return self.search([
            ("id", "not in", self._origin.ids),
            ("state", "!=", "done"),
            ("employee_ids", "in", self.employee_ids.ids),
            ("start_datetime", "<", self.end_datetime),
            ("end_datetime", ">", self.start_datetime),
        ])

    @api.depends("employee_ids", "start_datetime", "end_datetime", "state")
    def _compute_conflicts(self):
        for item in self:
            others = item._tectora_overlapping()
            item.conflict_planning_ids = others
            item.conflict_employee_ids = others.employee_ids & item.employee_ids
            item.has_conflict = bool(others)

    def _search_has_conflict(self, operator, value):
        values = list(value) if isinstance(value, (list, tuple, set)) else [value]
        wanted = any(values)
        positive = wanted if operator in ("=", "in") else not wanted
        self.flush_model(["start_datetime", "end_datetime", "state", "employee_ids"])
        self.env.cr.execute(
            """
            SELECT DISTINCT a.id
              FROM tectora_roof_planning a
              JOIN tectora_roof_planning_employee_rel ra ON ra.planning_id = a.id
              JOIN tectora_roof_planning_employee_rel rb
                ON rb.employee_id = ra.employee_id AND rb.planning_id != a.id
              JOIN tectora_roof_planning b ON b.id = rb.planning_id
             WHERE a.state != 'done' AND b.state != 'done'
               AND a.start_datetime < b.end_datetime
               AND a.end_datetime > b.start_datetime
            """
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        return [("id", "in" if positive else "not in", ids)]

    # ---------------------------------------------------------- planner
    @api.model
    def _drop_unavailable_views(self, action):
        """Strip view types the web client cannot render.

        The gantt view comes from web_gantt. When it is missing the client
        refuses the whole action with "View types not defined gantt" instead of
        falling back, and it reads that list from the session it was loaded
        with -- so a browser tab opened before the planner was installed hits
        the same error. Dropping the view type here degrades to list/form.
        """
        try:
            available = set(self.env["ir.ui.view"].get_view_info())
        except Exception:  # pragma: no cover - never break the button
            _logger.exception("Could not read the available view types")
            return action
        views = [
            view for view in action.get("views") or []
            if view[1] in available or view[1] == "search"
        ]
        kept = [view[1] for view in views if view[1] != "search"]
        if not kept:
            return action
        action["views"] = views
        action["view_mode"] = ",".join(kept)
        return action

    @api.model
    def _tectora_planner_action(self, xmlid=TEAM_PLANNER_XMLID):
        action = self.env["ir.actions.act_window"]._for_xml_id(xmlid)
        return self._drop_unavailable_views(action)

    def action_open_in_planner(self):
        """This block's project in the planner per employee: who works on it
        when, one row per employee."""
        self.ensure_one()
        action = self._tectora_planner_action(EMPLOYEE_PLANNER_XMLID)
        action["domain"] = [("project_id", "=", self.project_id.id)]
        action["context"] = {
            "default_project_id": self.project_id.id,
            "default_team_id": self.team_id.id,
            "initial_date": fields.Date.to_string(
                (self.start_datetime or fields.Datetime.now()).date()
            ),
        }
        return action

    def action_view_conflicts(self):
        """The blocks this one overlaps with, and itself, per employee."""
        self.ensure_one()
        blocks = self | self.conflict_planning_ids
        action = self._tectora_planner_action(EMPLOYEE_PLANNER_XMLID)
        action["name"] = _("Dubbel ingepland")
        action["domain"] = [("id", "in", blocks.ids)]
        action["context"] = {
            "initial_date": fields.Date.to_string(
                (self.start_datetime or fields.Datetime.now()).date()
            ),
        }
        return action
