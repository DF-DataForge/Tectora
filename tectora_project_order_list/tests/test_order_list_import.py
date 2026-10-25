# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_project_tasks.tools import xlsx

HEADER = ["Volgorde", "Onderdeel", "Actie", "Leveranciers", "Toelichting leveranciers"]


@tagged("post_install", "-at_install")
class TestOrderListImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["tectora.order.list.template"].search([]).action_archive()
        cls.Wizard = cls.env["tectora.order.list.import"]
        cls.supplier_a = cls.env["res.partner"].create({"name": "Leverancier A"})

    def _import(self, data, **values):
        wizard = self.Wizard.create({"file": base64.b64encode(data).decode(), "filename": "lijst.xlsx", **values})
        wizard.action_import()
        return wizard

    def _parts(self):
        return self.env["tectora.order.list.template"].search([])

    def test_standard_list_imports(self):
        wizard = self._import(self.Wizard._tectora_template_workbook())
        parts = self._parts()
        self.assertEqual(parts.mapped("name"), [
            "Dakbedekking (EPDM)", "Isolatie", "Dakranden en afwerkingsprofielen", "Bevestigingsmiddelen en lijm",
        ])
        self.assertEqual(parts.mapped("order_action"), ["order", "stock_first", "order", "stock_first"])
        self.assertEqual(parts[0].partner_ids, self.supplier_a, "B does not exist: skipped")
        self.assertIn("Leverancier B", wizard.summary)
        self.assertIn("Levertijd", parts[0].supplier_note)

    def test_create_missing_suppliers(self):
        self._import(self.Wizard._tectora_template_workbook(), create_suppliers=True)
        part = self._parts()[:1]
        self.assertEqual(part.partner_ids.mapped("name"), ["Leverancier A", "Leverancier B"])
        # the first supplier is the default one on a new project's order list
        project = self.env["project.project"].create({"name": "Werf"})
        self.assertEqual(project.tectora_order_line_ids[:1].partner_id, self.supplier_a)

    def test_update_and_replace(self):
        self._import(xlsx.build_workbook([("Bestellijst", HEADER, [
            [1, "Isolatie", "Bestellen", "", ""], [2, "Lijm", "", "", ""],
        ], [])]))
        self._import(xlsx.build_workbook([("Bestellijst", HEADER, [
            [1, "isolatie", "stock eerst", "Leverancier A", "nieuw"],
        ], [])]), mode="replace")
        part = self._parts()
        self.assertEqual(len(part), 1)
        self.assertEqual((part.name, part.order_action, part.supplier_note), ("isolatie", "stock_first", "nieuw"))
        self.assertEqual(part.partner_ids, self.supplier_a)

    def test_errors_import_nothing(self):
        data = xlsx.build_workbook([("Bestellijst", HEADER, [
            [1, "Isolatie", "Bellen", "", ""], ["een", "Lijm", "", "", ""], [3, "", "Bestellen", "", ""],
        ], [])])
        with self.assertRaises(UserError) as error:
            self._import(data)
        for row in ("Rij 2", "Rij 3", "Rij 4"):
            self.assertIn(row, str(error.exception))
        self.assertFalse(self._parts())
