# -*- coding: utf-8 -*-
"""The free moments of the teams, for the team planner's "Beschikbare
momenten": per team the working days (Monday to Friday) without a work block
in the coming weeks, as periods; for a project, how many days it takes that
team (its hours on the order over the team's members, 8 hours a day) and
which periods are long enough. A period can be planned at once: a concept
block for the project on that team."""
import math
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

HOURS_PER_DAY = 8.0
DAY_START = time(7, 30)
DAY_END = time(16, 30)


class TectoraRoofPlanning(models.Model):
    _inherit = "tectora.roof.planning"

    @api.model
    def _tectora_tz(self):
        return pytz.timezone(self.env.user.tz or "Europe/Brussels")

    @api.model
    def _tectora_project_hours(self, project):
        """The hours the project's order estimates (demolition + execution)."""
        order = project.sale_order_id if project else False
        if not order:
            return 0.0
        return (getattr(order, "tectora_demolition_hours", 0.0) or 0.0) + (
            getattr(order, "tectora_execution_hours", 0.0) or 0.0
        )

    @api.model
    def tectora_get_availability(self, project_id=False, weeks=8):
        """Per team its free periods in the coming ``weeks`` weeks, and for
        ``project_id`` the days it needs on that team."""
        tz = self._tectora_tz()
        today = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(tz).date()
        last = today + timedelta(days=int(weeks or 8) * 7)
        start_utc = tz.localize(datetime.combine(today, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = tz.localize(datetime.combine(last, time.max)).astimezone(pytz.utc).replace(tzinfo=None)
        project = self.env["tectora.roof.project"].browse(int(project_id or 0)).exists()
        hours = self._tectora_project_hours(project)
        teams = self.env["tectora.roof.team"].search([])
        blocks = self.search([
            ("team_id", "in", teams.ids),
            ("start_datetime", "<=", end_utc),
            ("end_datetime", ">=", start_utc),
        ])
        busy = {}
        for block in blocks:
            first = pytz.utc.localize(block.start_datetime).astimezone(tz)
            end = pytz.utc.localize(block.end_datetime).astimezone(tz)
            # A block ending at midnight does not take the next day.
            last_day = (end - timedelta(seconds=1)).date()
            day = first.date()
            while day <= last_day:
                busy.setdefault(block.team_id.id, set()).add(day)
                day += timedelta(days=1)
        result = []
        for team in teams:
            members = len(team.member_ids)
            needed = math.ceil(hours / (max(members, 1) * HOURS_PER_DAY)) if hours else 0
            windows = []
            current = None
            day = today
            while day <= last:
                if day.weekday() < 5:
                    if day not in busy.get(team.id, set()):
                        if current:
                            current["end"] = day
                            current["days"] += 1
                        else:
                            current = {"start": day, "end": day, "days": 1}
                    elif current:
                        windows.append(current)
                        current = None
                day += timedelta(days=1)
            if current:
                windows.append(current)
            result.append({
                "id": team.id,
                "name": team.name,
                "members": members,
                "needed": needed,
                "windows": [{
                    "start": fields.Date.to_string(w["start"]),
                    "end": fields.Date.to_string(w["end"]),
                    "days": w["days"],
                    "fits": bool(needed) and w["days"] >= needed,
                } for w in windows],
            })
        return {
            "project": {"id": project.id, "name": project.display_name, "hours": round(hours, 1)} if project else False,
            "weeks": int(weeks or 8),
            "teams": result,
        }

    @api.model
    def tectora_plan_at(self, project_id, team_id, start, stop):
        """A click (or drag) on the planner's cells, opened from a project:
        a concept block for the project on that row's team over the working
        days the cells cover. ``start`` / ``stop`` as the gantt gives them
        (UTC)."""
        tz = self._tectora_tz()
        first = pytz.utc.localize(fields.Datetime.to_datetime(start)).astimezone(tz).date()
        end = pytz.utc.localize(fields.Datetime.to_datetime(stop) - timedelta(seconds=1)).astimezone(tz).date()
        while first.weekday() >= 5 and first < end:
            first += timedelta(days=1)
        days = 0
        day = first
        while day <= end:
            if day.weekday() < 5:
                days += 1
            day += timedelta(days=1)
        return self.tectora_plan_window(project_id, team_id, fields.Date.to_string(first), max(days, 1))

    @api.model
    def tectora_plan_window(self, project_id, team_id, start, days):
        """A concept block for the project on the team, from ``start`` (a
        date) over ``days`` working days, 07:30 - 16:30."""
        project = self.env["tectora.roof.project"].browse(int(project_id or 0)).exists()
        team = self.env["tectora.roof.team"].browse(int(team_id or 0)).exists()
        if not project or not team:
            raise UserError(_("Kies een project en een ploeg."))
        tz = self._tectora_tz()
        day = fields.Date.to_date(start)
        remaining = max(int(days or 1), 1)
        last = day
        while remaining:
            if last.weekday() < 5:
                remaining -= 1
                if not remaining:
                    break
            last += timedelta(days=1)

        def utc(date, moment):
            return tz.localize(datetime.combine(date, moment)).astimezone(pytz.utc).replace(tzinfo=None)

        block = self.create({
            "project_id": project.id,
            "team_id": team.id,
            "employee_ids": [(6, 0, team.member_ids.ids)],
            "start_datetime": utc(day, DAY_START),
            "end_datetime": utc(last, DAY_END),
            "state": "draft",
        })
        return block.id
