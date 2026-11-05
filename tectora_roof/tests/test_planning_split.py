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
