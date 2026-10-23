# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTaskPhases(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Phase = cls.env["tectora.project.phase"]
        Template = cls.env["tectora.task.template"]
        # Start from an empty template, as the module ships it.
        Template.search([]).action_archive()
        Phase.search([]).action_archive()
        cls.phase_1 = Phase.create({"name": "Voorbereiding", "sequence": 1})
        cls.phase_2 = Phase.create({
            "name": "Uitvoering", "sequence": 2,
            "deadline_reference": "end", "deadline_offset": -2,
        })
        cls.main = Template.create({"name": "Plannen", "phase_id": cls.phase_1.id})
        cls.sub_a = Template.create({"name": "Ploeg", "phase_id": cls.phase_1.id, "parent_id": cls.main.id})
        cls.sub_b = Template.create({"name": "Materiaal", "phase_id": cls.phase_1.id, "parent_id": cls.main.id})
        cls.option = Template.create({"name": "Kraan", "phase_id": cls.phase_1.id, "optional": True})
        cls.execute = Template.create({
            "name": "Dak plaatsen", "phase_id": cls.phase_2.id,
            "deadline_reference": "start", "deadline_offset": 3,
        })

    def _project(self, **values):
        return self.env["project.project"].create({"name": "Werf", **values})

    def _task(self, project, template):
        return self.env["project.task"].with_context(active_test=False).search([
            ("project_id", "=", project.id), ("tectora_template_id", "=", template.id),
        ])

    def test_new_project_gets_phases_and_tasks(self):
        project = self._project(date_start=date(2026, 11, 2), date=date(2026, 11, 20))
        self.assertTrue(project.tectora_task_phases)
        milestones = project._tectora_phase_milestones()
        self.assertEqual(milestones.tectora_phase_id, self.phase_1 | self.phase_2)
        self.assertEqual(project.tectora_phase_id, self.phase_1)
        main = self._task(project, self.main)
        self.assertEqual(set(main.child_ids.mapped("name")), {"Ploeg", "Materiaal"})
        self.assertFalse(self._task(project, self.option).active, "options start switched off")
        self.assertEqual(milestones[1].deadline, date(2026, 11, 18))
        self.assertEqual(self._task(project, self.execute).date_deadline.date(), date(2026, 11, 5))

        # deadlines follow the project dates
        project.date_start = date(2026, 11, 9)
        self.assertEqual(self._task(project, self.execute).date_deadline.date(), date(2026, 11, 12))

    def test_ticking_off_reaches_the_phase(self):
        project = self._project()
        main = self._task(project, self.main)
        sub_a, sub_b = main.child_ids
        sub_a.action_tectora_toggle_done(done=True)
        self.assertNotEqual(main.state, "1_done")
        sub_b.action_tectora_toggle_done(done=True)
        self.assertEqual(main.state, "1_done", "all subtasks done -> main task done")
        milestone = project._tectora_phase_milestones()[0]
        self.assertTrue(milestone.is_reached, "the switched-off option does not block the phase")
        self.assertEqual(project.tectora_phase_id, self.phase_2)

        # switching the option on reopens the phase
        self._task(project, self.option).action_tectora_toggle_enabled()
        self.assertFalse(milestone.is_reached)

        # reopening a subtask reopens its main task
        sub_a.action_tectora_toggle_done(done=False)
        self.assertNotEqual(main.state, "1_done")

    def test_board_data(self):
        project = self._project()
        data = project.tectora_get_task_board_data()
        self.assertTrue(data["project"]["started"])
        self.assertEqual([p["name"] for p in data["phases"]], ["Voorbereiding", "Uitvoering"])
        self.assertEqual(data["phases"][0]["state"], "current")
        self.assertEqual(data["phases"][0]["total"], 1, "only the active main task counts")
        self.assertEqual(len(data["phases"][0]["tasks"][0]["children"]), 2)
        self.assertEqual([t["name"] for t in data["current_tasks"]], ["Plannen"])

    def test_without_phases_nothing_starts(self):
        self.env["tectora.project.phase"].search([]).action_archive()
        project = self._project()
        self.assertFalse(project.tectora_task_phases)
        data = project.tectora_get_task_board_data()
        self.assertFalse(data["project"]["started"])
        self.assertFalse(data["project"]["can_start"])

    def test_copy_does_not_duplicate_tasks(self):
        project = self._project()
        copy = project.copy()
        self.assertEqual(len(self._task(copy, self.main)), 1)
        self.assertEqual(len(copy._tectora_phase_milestones()), 2)
