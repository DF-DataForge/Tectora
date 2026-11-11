# -*- coding: utf-8 -*-
"""The teams' free moments in the team planner, and planning a project in
one of them."""
from datetime import datetime, time, timedelta

import pytz

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAvailability(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.user.tz = "Europe/Brussels"
        cls.team = cls.env["tectora.roof.team"].create({"name": "Ploeg test"})
        cls.project = cls.env["tectora.roof.project"].create({
            "name": "Beschikbaarheid", "partner_id": cls.env["res.partner"].create({"name": "Klant"}).id,
        })
        Planning = cls.env["tectora.roof.planning"]
        tz = pytz.timezone("Europe/Brussels")
        today = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(tz).date()
        # Next Monday to Wednesday busy.
        cls.monday = today + timedelta(days=(7 - today.weekday()))

        def utc(day, moment):
            return tz.localize(datetime.combine(day, moment)).astimezone(pytz.utc).replace(tzinfo=None)

        Planning.create({
            "project_id": cls.project.id, "team_id": cls.team.id,
            "start_datetime": utc(cls.monday, time(7, 30)),
            "end_datetime": utc(cls.monday + timedelta(days=2), time(16, 30)),
        })

    def test_free_periods(self):
        data = self.env["tectora.roof.planning"].tectora_get_availability(weeks=3)
        team = next(t for t in data["teams"] if t["id"] == self.team.id)
        starts = [w["start"] for w in team["windows"]]
        thursday = fields.Date.to_string(self.monday + timedelta(days=3))
        self.assertIn(thursday, starts, "free again after the block")
        for window in team["windows"]:
            start = fields.Date.to_date(window["start"])
            end = fields.Date.to_date(window["end"])
            self.assertFalse(start <= self.monday <= end, "the busy days are not free")

    def test_plan_window(self):
        Planning = self.env["tectora.roof.planning"]
        thursday = self.monday + timedelta(days=3)
        block = Planning.browse(Planning.tectora_plan_window(
            self.project.id, self.team.id, fields.Date.to_string(thursday), 3,
        ))
        tz = pytz.timezone("Europe/Brussels")
        end = pytz.utc.localize(block.end_datetime).astimezone(tz).date()
        # Thursday, Friday, Monday: three working days over the weekend.
        self.assertEqual(end, thursday + timedelta(days=4))
        self.assertEqual(block.state, "draft")

    def test_plan_at_cells(self):
        """A click on the planner's cells: the days they cover (here
        Thursday and Friday, as the gantt gives them in UTC)."""
        Planning = self.env["tectora.roof.planning"]
        tz = pytz.timezone("Europe/Brussels")
        thursday = self.monday + timedelta(days=3)

        def utc(day):
            return fields.Datetime.to_string(
                tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
            )

        block = Planning.browse(Planning.tectora_plan_at(
            self.project.id, self.team.id, utc(thursday), utc(thursday + timedelta(days=2)),
        ))
        local_start = pytz.utc.localize(block.start_datetime).astimezone(tz)
        local_end = pytz.utc.localize(block.end_datetime).astimezone(tz)
        self.assertEqual((local_start.date(), local_end.date()), (thursday, thursday + timedelta(days=1)))
        self.assertEqual(block.team_id, self.team)

    def test_teams_always_on_the_planner(self):
        Team = self.env["tectora.roof.team"]
        shown = Team.create({"name": "Altijd zichtbaar", "show_in_planner": True})
        hidden = Team.create({"name": "Enkel met blokken"})
        Planning = self.env["tectora.roof.planning"]
        rows = Planning._read_group_team_id(Team, [])
        self.assertIn(shown, rows)
        self.assertNotIn(hidden, rows)
        # Filtered on a team: only what the filter asks.
        self.assertEqual(Planning._read_group_team_id(Team, [("team_id", "=", hidden.id)]), Team)
