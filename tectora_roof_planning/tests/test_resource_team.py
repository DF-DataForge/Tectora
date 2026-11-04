# -*- coding: utf-8 -*-
"""The planner per resource groups its employees team by team."""
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_roof_planning.hooks import TEAM_GROUP_FILTER, _team_first_context


@tagged("post_install", "-at_install")
class TestResourceTeam(TransactionCase):

    def test_shift_carries_the_team_of_its_employee(self):
        team = self.env["tectora.roof.team"].create({"name": "Ploeg Noord"})
        other = self.env["tectora.roof.team"].create({"name": "Ploeg Zuid"})
        employee = self.env["hr.employee"].create({"name": "Jan", "roof_team_id": team.id})
        slot = self.env["planning.slot"].create({
            "resource_ids": [(6, 0, employee.resource_id.ids)],
            "start_datetime": "2026-11-02 07:00:00",
            "end_datetime": "2026-11-02 16:00:00",
        })
        self.assertEqual(slot.tectora_resource_team_id, team)
        employee.roof_team_id = other
        self.assertEqual(slot.tectora_resource_team_id, other, "follows the employee's team")

    def test_resource_planner_grouped_by_team_first(self):
        context = _team_first_context("{'search_default_group_by_resource': 1, 'x': 1}")
        self.assertTrue(context.startswith("{'%s': 1" % TEAM_GROUP_FILTER))
        self.assertIn("'search_default_group_by_resource': 2", context)
        self.assertEqual(
            _team_first_context("{'group_by': ['resource_ids']}"),
            "{'group_by': ['tectora_resource_team_id', 'resource_ids']}",
        )
        self.assertIsNone(_team_first_context(context), "only once")
        self.assertIsNone(_team_first_context("{'search_default_group_by_role': 1}"))
