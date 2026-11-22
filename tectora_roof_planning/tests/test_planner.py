# -*- coding: utf-8 -*-
"""The project planner: planning on a project of the Project app, the
planned hours and who is planned twice."""
from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectPlanner(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.user.tz = "Europe/Brussels"
        cls.Planning = cls.env["tectora.roof.planning"]
        cls.team = cls.env["tectora.roof.team"].create({"name": "Ploeg Noord"})
        cls.jan = cls.env["hr.employee"].create({"name": "Jan", "roof_team_id": cls.team.id})
        cls.piet = cls.env["hr.employee"].create({"name": "Piet", "roof_team_id": cls.team.id})
        cls.roof = cls.env["tectora.roof.project"].create({"name": "Werf A"})
        cls.other_roof = cls.env["tectora.roof.project"].create({"name": "Werf B"})

    def _block(self, roof, start, end, employees=None, **values):
        return self.Planning.create(dict({
            "project_id": roof.id,
            "team_id": self.team.id,
            "employee_ids": [(6, 0, (employees or self.jan | self.piet).ids)],
            "start_datetime": start,
            "end_datetime": end,
        }, **values))

    def test_planned_on_a_project_of_the_project_app(self):
        """A block planned on a project is planned on its roof project; a
        project without one gets it."""
        dossier = self.env["project.project"].create({"name": "Los project"})
        block = self.Planning.create({
            "dossier_id": dossier.id,
            "team_id": self.team.id,
            "start_datetime": datetime(2026, 11, 16, 7, 0),
            "end_datetime": datetime(2026, 11, 16, 16, 0),
        })
        self.assertTrue(block.project_id, "the project got its roof project")
        self.assertEqual(block.project_id.project_id, dossier)
        self.assertEqual(block.dossier_id, dossier)
        self.assertEqual(dossier.roof_project_id.planning_ids, block)

        # A roof project's block follows the project made for it later.
        loose = self._block(self.roof, datetime(2026, 11, 17, 7, 0), datetime(2026, 11, 17, 16, 0))
        self.assertFalse(loose.dossier_id)
        self.roof._ensure_project()
        self.assertEqual(loose.dossier_id, self.roof.project_id)

        # Moved to another project in the planner per project.
        loose.dossier_id = dossier
        self.assertEqual(loose.project_id, dossier.roof_project_id)

    def test_planned_hours(self):
        # Monday 8:00 to Friday 17:00 (Brussels, UTC+1): 5 working days.
        week = self._block(self.roof, datetime(2026, 11, 16, 7, 0), datetime(2026, 11, 20, 16, 0))
        self.assertEqual(week.planned_hours, 5 * 8 * 2)
        # Friday to Monday: the weekend does not count.
        weekend = self._block(
            self.roof, datetime(2026, 11, 20, 7, 0), datetime(2026, 11, 23, 16, 0),
            employees=self.jan,
        )
        self.assertEqual(weekend.planned_hours, 2 * 8)
        # A morning.
        morning = self._block(
            self.roof, datetime(2026, 11, 24, 7, 0), datetime(2026, 11, 24, 11, 0),
            employees=self.jan,
        )
        self.assertEqual(morning.planned_hours, 4)

    def test_planned_twice(self):
        first = self._block(self.roof, datetime(2026, 11, 16, 7, 0), datetime(2026, 11, 18, 16, 0))
        second = self._block(
            self.other_roof, datetime(2026, 11, 18, 7, 0), datetime(2026, 11, 19, 16, 0),
            employees=self.piet,
        )
        later = self._block(
            self.other_roof, datetime(2026, 11, 23, 7, 0), datetime(2026, 11, 23, 16, 0),
        )
        self.assertTrue(first.has_conflict)
        self.assertEqual(first.conflict_employee_ids, self.piet)
        self.assertEqual(first.conflict_planning_ids, second)
        self.assertTrue(second.has_conflict)
        self.assertFalse(later.has_conflict)
        conflicting = self.Planning.search([("has_conflict", "=", True)])
        self.assertIn(first, conflicting)
        self.assertIn(second, conflicting)
        self.assertNotIn(later, conflicting)
        self.assertIn(later, self.Planning.search([("has_conflict", "=", False)]))
        # Work that is done no longer counts.
        second.action_set_done()
        first.invalidate_recordset()
        self.assertFalse(first.has_conflict)

    def test_planner_actions(self):
        block = self._block(self.roof, datetime(2026, 11, 16, 7, 0), datetime(2026, 11, 16, 16, 0))
        action = self.roof.action_view_planning()
        self.assertEqual(action["res_model"], "tectora.roof.planning")
        self.assertEqual(action["context"]["tectora_project_id"], self.roof.id)
        per_employee = block.action_open_in_planner()
        self.assertEqual(per_employee["domain"], [("project_id", "=", self.roof.id)])
        for xmlid in ("menu_project_planner_team", "menu_project_planner_employee",
                      "menu_project_planner_project"):
            menu = self.env.ref("tectora_roof_planning.%s" % xmlid)
            self.assertEqual(menu.parent_id.parent_id, self.env.ref("project.menu_main_pm"))
