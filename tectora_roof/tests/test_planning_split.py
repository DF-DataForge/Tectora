# -*- coding: utf-8 -*-
"""The scissors of the team planner: a work block cut in two at a day."""
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanningSplit(TransactionCase):

    def test_cut_at_a_day(self):
        self.env.user.tz = "Europe/Brussels"
        roof = self.env["tectora.roof.project"].create({"name": "Werf"})
        team = self.env["tectora.roof.team"].create({"name": "Ploeg Noord"})
        block = self.env["tectora.roof.planning"].create({
            "project_id": roof.id,
            "team_id": team.id,
            # Monday 07:00 to Wednesday 16:00, Brussels (UTC+1 in November)
            "start_datetime": datetime(2026, 11, 2, 6, 0),
            "end_datetime": datetime(2026, 11, 4, 15, 0),
        })
        block.action_tectora_split_at("2026-11-04")
        second = self.env["tectora.roof.planning"].search(
            [("project_id", "=", roof.id), ("id", "!=", block.id)]
        )
        # Cut at Wednesday 00:00 Brussels = Tuesday 23:00 UTC.
        self.assertEqual(block.end_datetime, datetime(2026, 11, 3, 23, 0))
        self.assertEqual(second.start_datetime, datetime(2026, 11, 3, 23, 0))
        self.assertEqual(second.end_datetime, datetime(2026, 11, 4, 15, 0))
        self.assertEqual(second.team_id, team)
        with self.assertRaises(UserError, msg="only inside the block"):
            block.action_tectora_split_at("2026-11-10")


@tagged("post_install", "-at_install")
class TestPlanningWorkingHours(TransactionCase):
    """A period picked on the calendar runs 8:00 - 17:00 per day."""

    def test_days_picked(self):
        import pytz
        from datetime import datetime, time
        env = self.env
        env.user.tz = "Europe/Brussels"
        tz = pytz.timezone("Europe/Brussels")

        def utc(day, moment):
            return tz.localize(datetime.combine(day, moment)).astimezone(pytz.utc).replace(tzinfo=None)

        Planning = env["tectora.roof.planning"]
        monday = datetime(2026, 11, 16).date()
        friday = datetime(2026, 11, 20).date()
        # Monday to Friday picked: Monday 8:00 - Friday 17:00.
        start, end = Planning._tectora_working_hours(utc(monday, time.min), utc(friday, time.min))
        self.assertEqual(start, utc(monday, time(8, 0)))
        self.assertEqual(end, utc(friday, time(17, 0)))
        # The planner's cells end at the next midnight: Monday to Thursday.
        start, end = Planning._tectora_working_hours(utc(monday, time.min), utc(friday, time.min), exclusive_end=True)
        self.assertEqual(end, utc(datetime(2026, 11, 19).date(), time(17, 0)))
        start, end = Planning._tectora_working_hours(utc(monday, time.min), utc(friday, time(23, 59, 59)))
        self.assertEqual(end, utc(friday, time(17, 0)))
        # An end before the start: the start's day.
        start, end = Planning._tectora_working_hours(utc(friday, time.min), utc(monday, time.min))
        self.assertEqual((start, end), (utc(friday, time(8, 0)), utc(friday, time(17, 0))))
        # Hours set on purpose are kept.
        start, end = Planning._tectora_working_hours(utc(monday, time(9, 30)), utc(monday, time(12, 0)))
        self.assertEqual((start, end), (utc(monday, time(9, 30)), utc(monday, time(12, 0))))
