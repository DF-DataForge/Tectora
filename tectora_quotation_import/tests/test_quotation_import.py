# -*- coding: utf-8 -*-
import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_quote_rules import HEADER, row


class ImportCase(TransactionCase):
    """Taxes, stages and a works item; the helpers that run an import."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Odoo's own stages, renamed at Tectora.
        cls.stage_open = cls.env.ref("crm.stage_lead3")
        cls.stage_open.name = "Lopende offerte"
        cls.stage_won = cls.env.ref("crm.stage_lead4")
        cls.stage_won.name = "Gewonnen"
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

    def _import(self, rows, max_quotes=None, **options):
        """Run the wizard and, unless it is a test run, the import job it
        starts (without commits, as the scheduled action would)."""
        wizard = self.env["tectora.quotation.import"].create({
            "file": self._file(rows),
            "filename": "offertes.xlsx",
            "tax_0_id": self.taxes[0].id,
            "tax_6_id": self.taxes[6].id,
            "tax_21_id": self.taxes[21].id,
            **options,
        })
        action = wizard.action_import()
        if wizard.dry_run:
            return wizard
        job = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(job.state, "queued")
        job._process(commit=False, max_quotes=max_quotes)
        return job

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



@tagged("post_install", "-at_install")
class TestQuotationImport(ImportCase):

    def test_import_states_and_opportunities(self):
        job = self._import(self._rows())
        self.assertIn("3 offertes aangemaakt", job.summary)

        running = self._order("2026/0001")
        self.assertEqual(running.name, "2026/0001")
        self.assertEqual(running.state, "sent")
        self.assertEqual(running.client_order_ref, "Dak garage")
        self.assertEqual(str(running.date_order.date()), "2026-01-19")
        self.assertEqual(str(running.validity_date), "2026-02-03")
        self.assertEqual(running.opportunity_id.stage_id, self.stage_open)
        self.assertEqual(running.opportunity_id.partner_id, running.partner_id)
        self.assertAlmostEqual(running.amount_untaxed, 104.30)
        lines = running.order_line.filtered(lambda l: not l.display_type).sorted("sequence")
        self.assertEqual(len(lines), 2)
        self.assertFalse(running.order_line.filtered("display_type"),
                         "a title without lines is left out")
        self.assertEqual(lines[0].product_id, self.works_item)
        self.assertEqual(lines[0].label, self.works_item.display_name,
                         "a catalogue works item is shown once, as Odoo shows it")
        self.assertEqual(lines[0].price_unit, 22.15, "the old price, not the catalogue's")
        self.assertEqual(lines[0].tax_ids, self.taxes[6])
        generic = lines[1]
        meter = self.env.ref("uom.product_uom_meter")
        self.assertEqual(generic.product_id.default_code, "TECTORA-IMPORT-%s" % meter.id)
        self.assertEqual(generic.product_id.uom_id, meter, "no unit conversion on the quote")
        self.assertEqual(generic.name, "Speciale opstand")
        self.assertEqual(generic.label, "Speciale opstand",
                         "the generic works item shows only the description")
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
        job = self._import(self._rows(first_status="goedgekeurd"))
        self.assertEqual(len(self._order("2026/0001")), 1)
        self.assertEqual(len(self._order("2026/0002")), 1)
        self.assertIn("0 offertes aangemaakt", job.summary)
        self.assertEqual(running.state, "sale")
        self.assertEqual(running.tectora_legacy_status, "goedgekeurd")
        self.assertEqual(running.opportunity_id.stage_id, self.stage_won)
        # A confirmed order never goes back to a quotation.
        self._import(self._rows(first_status="openstaand"))
        self.assertEqual(running.state, "sale")

    def test_dry_run_and_resume(self):
        wizard = self._import(self._rows(), dry_run=True)
        self.assertIn("TESTRUN", wizard.summary)
        self.assertIn("3 nieuwe offertes", wizard.summary)
        self.assertFalse(self._order("2026/0001"))
        # An import interrupted after one quotation goes on where it stopped.
        job = self._import(self._rows(), max_quotes=1)
        self.assertEqual(job.state, "running")
        self.assertEqual(job.position, 1)
        self.assertTrue(self._order("2026/0001"))
        self.assertFalse(self._order("2026/0002"))
        job._process(commit=False)
        self.assertEqual(job.state, "done")
        self.assertEqual(job.progress, 100)
        self.assertEqual(len(self._order("2026/0001")), 1)
        self.assertTrue(self._order("2026/0003"))
        self.assertIn("3 offertes aangemaakt", job.summary)

    def test_sections(self):
        def quote_row(description, quantity, unit, price):
            return row("2026/0010", description, quantity, unit, price, quantity * price,
                       customer="Mevr. Claeys", vat_number="")
        rows = [  # alphabetical, as the export gives them
            quote_row("Actie maand februari", 1, "st", -50),
            quote_row("AFBOUWWERKEN THV HET PLAT DAK", 0, "", 0),
            quote_row("ALGEMENE NOTA'S", 0, "", 0),
            quote_row("ALGEMENE WERKEN", 0, "", 0),
            quote_row("Algemene vaste kosten", 1, "stuks", 85),
            quote_row("COMMERCIËLE TEGEMOETKOMING", 0, "", 0),
            quote_row("Leveren en plaatsen van de PE-tapbuis", 1, "st", 120),
            quote_row("OPBOUWWERKEN THV HET PLAT DAK", 0, "", 0),
            quote_row("Verwijderen van de tapbuis", 1, "st", 22.15),
        ]
        job = self._import(rows)
        order = self._order("2026/0010")
        self.assertEqual(order.order_line.sorted("sequence").mapped("label"), [
            "ALGEMENE WERKEN",
            "Algemene vaste kosten",
            "AFBOUWWERKEN THV HET PLAT DAK",
            "Verwijderen van de tapbuis",
            "OPBOUWWERKEN THV HET PLAT DAK",
            "Leveren en plaatsen van de PE-tapbuis",
            "COMMERCIËLE TEGEMOETKOMING",
            "Actie maand februari",
        ])
        sections = order.order_line.filtered(lambda l: l.display_type == "line_section")
        self.assertEqual(len(sections), 4)
        self.assertIn("4 secties", job.summary)
        self.assertAlmostEqual(order.amount_untaxed, 177.15)

    def test_titles_skipped(self):
        self._import(self._rows(), text_lines="skip")
        self.assertFalse(self._order("2026/0001").order_line.filtered("display_type"))

    def test_unknown_status_stops_the_import(self):
        rows = [row("2026/0009", "Verwijderen van de tapbuis", 1, "st", 25, 25,
                    status="in opmaak")]
        with self.assertRaisesRegex(UserError, "in opmaak"):
            self._import(rows)
        self.assertFalse(self._order("2026/0009"))


PROJECT_HEADER = (
    "nummer", "naam", "klantnummer", "klantnaam", "BTW-nummer klant", "adres klant",
    "postcode klant", "stad klant", "land klant", "adres project", "postcode project",
    "stad project", "omschrijving", "referentie voor klant", "status", "deadline",
    "verantwoordelijke gebruiker", "totaal offertes ex BTW",
)


def project_row(number, customer, total, status, deadline="", responsible="",
                description=""):
    return (number, "Roeselare - %s" % customer, "K001", customer, "", "Kerkstraat 1",
            "8800", "Roeselare", "", "Werfstraat 9", "8800", "Roeselare", description,
            "", status, deadline, responsible, total)


@tagged("post_install", "-at_install")
class TestProjectImport(ImportCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team_1 = cls.env["tectora.roof.team"].create({"name": "Team 1"})
        cls.team_2 = cls.env["tectora.roof.team"].create({"name": "Team 2"})

    def _import_projects(self, rows, **options):
        import openpyxl
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Export Simpla"
        sheet.append(PROJECT_HEADER)
        for values in rows:
            sheet.append(values)
        buffer = io.BytesIO()
        workbook.save(buffer)
        wizard = self.env["tectora.project.import"].create({
            "file": base64.b64encode(buffer.getvalue()).decode(),
            "filename": "projecten.xlsx",
            **options,
        })
        action = wizard.action_import()
        if wizard.dry_run:
            return wizard
        job = self.env[action["res_model"]].browse(action["res_id"])
        job._process(commit=False)
        return job

    def test_projects_linked_and_planned(self):
        self._import(self._rows())
        rows = [
            project_row("2026/0100", "Garage Noord BV", 25, "in uitvoering",
                        "30/10/2026", "TEAM 1 TECTORA: MARIUSZ & MARCIN",
                        "Branden van het dampscherm"),
            project_row("2026/0101", "Garage Noord BV", 100, "afgesloten",
                        "15/09/2026", "TEAM 1 + TEAM 2"),
            project_row("2026/0102", "Dhr. Peeters", 104.30, "lopend", "", "Onbekend BV"),
            project_row("2026/0103", "Mevr. Niemand", 0, "lopend"),
        ]
        preview = self._import_projects(rows, dry_run=True, create_missing_teams=False)
        self.assertIn("3 projecten gevonden", preview.summary)
        self.assertIn("GEEN PLOEG", preview.summary)
        self.assertFalse(self.env["tectora.project.import.team"].search([]))

        job = self._import_projects(rows, create_missing_teams=False)
        self.assertEqual(job.state, "done", job.summary)

        approved = self._order("2026/0003").roof_project_id
        self.assertEqual(approved.tectora_legacy_project_number, "2026/0100")
        self.assertEqual(approved.team_id, self.team_1)
        self.assertEqual(str(approved.date_deadline), "2026-10-30")
        self.assertEqual(approved.address, "Werfstraat 9, 8800 Roeselare")
        self.assertIn("dampscherm", str(approved.project_id.description))
        block = approved.planning_ids
        self.assertEqual(len(block), 1)
        self.assertEqual(block.team_id, self.team_1)
        self.assertEqual(block.state, "published")

        # The invoiced order had no roof project: it gets one, and a project.
        invoiced = self._order("2026/0002").roof_project_id
        self.assertTrue(invoiced.project_id)
        self.assertEqual(invoiced.state, "done")
        self.assertEqual(invoiced.planning_ids.state, "done")
        self.assertEqual(invoiced.planning_ids.employee_ids,
                         (self.team_1 | self.team_2).member_ids)

        # A quotation not confirmed yet: linked, no project; no team known.
        running = self._order("2026/0001").roof_project_id
        self.assertEqual(running.tectora_legacy_project_number, "2026/0102")
        self.assertFalse(running.team_id)
        self.assertIn("Onbekend BV (1)", job.summary)
        self.assertIn("2026/0103", job.summary)  # no order found

        # Again: nothing doubles; a corrected team table is applied.
        self.env["tectora.project.import.team"].search([("name", "=", "Onbekend BV")]).team_ids = self.team_2
        job = self._import_projects(rows, create_missing_teams=False)
        self.assertEqual(running.team_id, self.team_2)
        self.assertEqual(len(approved.planning_ids), 1)
        self.assertIn("3 bijgewerkt", job.summary)

    def test_missing_team_created(self):
        self._import(self._rows())
        rows = [project_row("2026/0102", "Dhr. Peeters", 104.30, "lopend", "30/10/2026",
                            "MIKO ROOF")]
        preview = self._import_projects(rows, dry_run=True)
        self.assertIn("NIEUWE PLOEG 'MIKO ROOF'", preview.summary)
        self.assertFalse(self.env["tectora.roof.team"].search([("name", "=", "MIKO ROOF")]))
        self._import_projects(rows)
        team = self.env["tectora.roof.team"].search([("name", "=", "MIKO ROOF")])
        self.assertEqual(len(team), 1)
        self.assertEqual(self._order("2026/0001").roof_project_id.team_id, team)
        self.assertEqual(
            self.env["tectora.project.import.team"].search([("name", "=", "MIKO ROOF")]).team_ids,
            team,
        )
        # Again: the same team, not a second one.
        self._import_projects(rows)
        self.assertEqual(self.env["tectora.roof.team"].search_count([("name", "=", "MIKO ROOF")]), 1)
