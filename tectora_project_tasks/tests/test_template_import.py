# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_project_tasks.tools import xlsx

HEADER = ["Fase", "Omschrijving fase", "Taak", "Subtaak", "Optie", "Deadline t.o.v.", "Dagen", "Toelichting"]


@tagged("post_install", "-at_install")
class TestTaskTemplateImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["tectora.task.template"].search([]).action_archive()
        cls.env["tectora.project.phase"].search([]).action_archive()
        cls.Wizard = cls.env["tectora.task.template.import"]

    def _import(self, data, mode="update"):
        wizard = self.Wizard.create({"file": base64.b64encode(data).decode(), "filename": "lijst.xlsx", "mode": mode})
        wizard.action_import()
        return wizard

    def _templates(self, **domain):
        return self.env["tectora.task.template"].search(
            [(key, "=", value) for key, value in domain.items()]
        )

    def test_standard_list_imports(self):
        """The list to download imports as it is."""
        data = self.Wizard._tectora_template_workbook()
        wizard = self._import(data)
        self.assertEqual(wizard.state, "done")
        phases = self.env["tectora.project.phase"].search([])
        self.assertEqual(phases.mapped("name"), ["Voorbereiding", "Uitvoering", "Oplevering"])
        self.assertEqual(phases[0].subtitle, "vóór de uitvoering")
        self.assertEqual((phases[2].deadline_reference, phases[2].deadline_offset), ("end", 7))
        ordered = self._templates(name="Materiaal besteld")
        self.assertEqual((ordered.deadline_reference, ordered.deadline_offset), ("start", -7))
        self.assertEqual(ordered.child_ids.mapped("name"), ["Isolatie", "Dakbedekking"])
        self.assertIn("bestellijst", ordered.description)
        self.assertTrue(self._templates(name="Kraan reserveren").optional)
        self.assertEqual(len(self._templates(parent_id=False)), 6)
        if "order_list_auto" in ordered._fields:
            self.assertTrue(ordered.order_list_auto)

    def test_reimport_updates_without_duplicates(self):
        rows = [["Voorbereiding", "", "Werfbezoek", "", "", "start", -14, ""]]
        self._import(xlsx.build_workbook([("Taaksjablonen", HEADER, rows, [])]))
        rows = [["Voorbereiding", "", "werfbezoek", "", "ja", "einde", -2, "Nieuw"],
                ["Voorbereiding", "", "Werfbezoek", "Foto's", "", "", "", ""]]
        wizard = self._import(xlsx.build_workbook([("Taaksjablonen", HEADER, rows, [])]))
        task = self._templates(parent_id=False)
        self.assertEqual(len(task), 1, "same name (any case) = the same task")
        self.assertEqual((task.optional, task.deadline_reference, task.deadline_offset), (True, "end", -2))
        self.assertEqual(task.child_ids.name, "Foto's")
        self.assertIn("1 bijgewerkt", wizard.summary)

    def test_replace_archives_the_rest(self):
        self._import(xlsx.build_workbook([("Taaksjablonen", HEADER, [
            ["Fase A", "", "Taak 1", "", "", "", "", ""],
            ["Fase B", "", "Taak 2", "", "", "", "", ""],
        ], [])]))
        self._import(xlsx.build_workbook([("Taaksjablonen", HEADER, [
            ["Fase A", "", "Taak 1", "", "", "", "", ""],
        ], [])]), mode="replace")
        self.assertEqual(self._templates().mapped("name"), ["Taak 1"])
        self.assertEqual(self.env["tectora.project.phase"].search([]).mapped("name"), ["Fase A"])

    def test_errors_import_nothing(self):
        rows = [["Fase A", "", "Taak 1", "", "", "morgen", -1, ""],
                ["Fase A", "", "", "", "", "", "", ""],
                ["Fase A", "", "Taak 3", "", "misschien", "", "x", ""]]
        with self.assertRaises(UserError) as error:
            self._import(xlsx.build_workbook([("Taaksjablonen", HEADER, rows, [])]))
        message = str(error.exception)
        self.assertIn("rij 2", message)
        self.assertIn("rij 3", message)
        self.assertIn("rij 4", message)
        self.assertFalse(self._templates())

    def test_missing_column(self):
        data = xlsx.build_workbook([("Taaksjablonen", ["Fase", "Omschrijving"], [["Fase A", ""]], [])])
        with self.assertRaisesRegex(UserError, "Taak"):
            self._import(data)
