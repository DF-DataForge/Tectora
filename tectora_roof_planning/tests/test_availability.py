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
