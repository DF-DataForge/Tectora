# -*- coding: utf-8 -*-
import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_quote_rules import HEADER, row


@tagged("post_install", "-at_install")
class TestQuotationImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Stage = cls.env["crm.stage"]
        cls.stage_open = Stage.create({"name": "Lopende offerte", "sequence": 50})
        cls.stage_won = Stage.create({"name": "Gewonnen", "sequence": 60, "is_won": True})
        # The won stage of the import is the one called "Gewonnen".
        Stage.search([("is_won", "=", True), ("id", "!=", cls.stage_won.id)]).write(
            {"sequence": 70}
        )
        Tax = cls.env["account.tax"]
        cls.taxes = {
            rate: Tax.create({
                "name": "%s%% S (import)" % rate,
                "amount": rate,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": cls.env.company.id,
                "sequence": 1,
            })
            for rate in (0, 6, 21)
        }
        cls.works_item = cls.env["product.product"].create({
            "name": "Verwijderen van de tapbuis",
            "type": "service",
            "sale_ok": True,
            "list_price": 30.0,
        })

    # ------------------------------------------------------------- helpers
    def _file(self, rows):
        import openpyxl
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Export Simpla"
        sheet.append(HEADER)
        for values in rows:
            sheet.append(values)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return base64.b64encode(buffer.getvalue()).decode()

    def _import(self, rows, **options):
        wizard = self.env["tectora.quotation.import"].create({
            "file": self._file(rows),
            "filename": "offertes.xlsx",
            "tax_0_id": self.taxes[0].id,
            "tax_6_id": self.taxes[6].id,
            "tax_21_id": self.taxes[21].id,
            **options,
        })
        wizard.action_import()
        return wizard

    def _order(self, number):
        return self.env["sale.order"].search([("tectora_legacy_number", "=", number)])

    def _rows(self, first_status="openstaand"):
        return [
            row("2026/0001", "Verwijderen van de tapbuis", 2, "st", 22.15, 44.30,
                status=first_status, customer="Dhr. Peeters",
                notes="Dit document werd digitaal ondertekend"),
            row("2026/0001", "Speciale opstand", 3, "lm BLAUW", 10, 60,
                status=first_status, customer="Dhr. Peeters"),
            row("2026/0001", "ALGEMENE WERKEN", 0, "", 0, 0,
                status=first_status, customer="Dhr. Peeters"),
            row("2026/0002", "Afvalverwerking forfaitair", 1, "sog", 100, 100,
                status="gefactureerd", vat=21, customer="Garage Noord BV", vat_number=""),
            row("2026/0003", "Verwijderen van de tapbuis", 1, "st", 25, 25,
                status="goedgekeurd", vat=0, customer="Garage Noord BV", vat_number=""),
        ]

    # --------------------------------------------------------------- tests
    def test_import_states_and_opportunities(self):
        wizard = self._import(self._rows())
        self.assertIn("3 offertes aangemaakt", wizard.summary)

        running = self._order("2026/0001")
        self.assertEqual(running.name, "2026/0001")
        self.assertEqual(running.state, "sent")
        self.assertEqual(running.client_order_ref, "Dak garage")
        self.assertEqual(str(running.date_order.date()), "2026-01-19")
        self.assertEqual(str(running.validity_date), "2026-02-03")
        self.assertEqual(running.opportunity_id.stage_id, self.stage_open)
        self.assertEqual(running.opportunity_id.partner_id, running.partner_id)
        self.assertAlmostEqual(running.amount_untaxed, 104.30)
        lines = running.order_line.sorted("sequence")
        self.assertEqual(len(lines), 2, "the title line is skipped")
        self.assertEqual(lines[0].product_id, self.works_item)
        self.assertEqual(lines[0].price_unit, 22.15, "the old price, not the catalogue's")
        self.assertEqual(lines[0].tax_ids, self.taxes[6])
        generic = lines[1]
        self.assertEqual(generic.product_id.default_code, "TECTORA-IMPORT")
        self.assertEqual(generic.name, "Speciale opstand")
        self.assertEqual(generic.product_uom_qty, 6, "the multiplied line takes the factor")
        self.assertEqual(generic.product_uom_id, self.env.ref("uom.product_uom_meter"))
        self.assertTrue(running.roof_project_id)
        self.assertTrue(any(
            "digitaal ondertekend" in str(body) for body in running.message_ids.mapped("body")
        ))
        # A quantity change keeps the old price.
        generic.product_uom_qty = 7
        self.assertEqual(generic.price_unit, 10)

        invoiced = self._order("2026/0002")
        self.assertEqual(invoiced.state, "sale")
        self.assertEqual(str(invoiced.date_order.date()), "2026-01-19")
        self.assertEqual(invoiced.invoice_status, "invoiced")
        self.assertEqual(invoiced.tectora_legacy_invoiced, "invoiced")
        self.assertFalse(invoiced.roof_project_id, "a finished site gets no roof project")
        self.assertEqual(invoiced.opportunity_id.stage_id, self.stage_won)
        self.assertEqual(invoiced.opportunity_id.probability, 100)
        self.assertEqual(invoiced.order_line.tax_ids, self.taxes[21])

        approved = self._order("2026/0003")
        self.assertEqual(approved.state, "sale")
        self.assertEqual(approved.invoice_status, "to invoice")
        self.assertTrue(approved.roof_project_id)
        self.assertEqual(approved.opportunity_id.stage_id, self.stage_won)
        self.assertEqual(approved.order_line.tax_ids, self.taxes[0])
        self.assertEqual(approved.partner_id, invoiced.partner_id, "one customer, once")
        self.assertNotEqual(approved.partner_id, running.partner_id)
        self.assertEqual(running.partner_id.vat, "BE0477472701")

    def test_reimport_never_duplicates_and_moves_forward(self):
        self._import(self._rows())
        running = self._order("2026/0001")
        wizard = self._import(self._rows(first_status="goedgekeurd"))
        self.assertEqual(len(self._order("2026/0001")), 1)
        self.assertEqual(len(self._order("2026/0002")), 1)
        self.assertIn("0 offertes aangemaakt", wizard.summary)
        self.assertEqual(running.state, "sale")
        self.assertEqual(running.tectora_legacy_status, "goedgekeurd")
        self.assertEqual(running.opportunity_id.stage_id, self.stage_won)
        # A confirmed order never goes back to a quotation.
        self._import(self._rows(first_status="openstaand"))
        self.assertEqual(running.state, "sale")

    def test_dry_run_and_limit(self):
        wizard = self._import(self._rows(), dry_run=True)
        self.assertIn("TESTRUN", wizard.summary)
        self.assertFalse(self._order("2026/0001"))
        self._import(self._rows(), limit=1)
        self.assertTrue(self._order("2026/0001"))
        self.assertFalse(self._order("2026/0002"))
        self._import(self._rows(), limit=1)
        self.assertTrue(self._order("2026/0002"))

    def test_text_lines_as_notes(self):
        self._import(self._rows(), text_lines="note")
        notes = self._order("2026/0001").order_line.filtered(
            lambda line: line.display_type == "line_note"
        )
        self.assertEqual(notes.mapped("name"), ["ALGEMENE WERKEN"])

    def test_unknown_status_stops_the_import(self):
        rows = [row("2026/0009", "Verwijderen van de tapbuis", 1, "st", 25, 25,
                    status="in opmaak")]
        with self.assertRaisesRegex(UserError, "in opmaak"):
            self._import(rows)
        self.assertFalse(self._order("2026/0009"))
