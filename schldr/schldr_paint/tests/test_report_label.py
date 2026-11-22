# -*- coding: utf-8 -*-
"""The quotation and invoice PDFs name the product without its internal
reference."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReportLabel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.partner = cls.env["res.partner"].create({"name": "Klant"})
        cls.product = cls.env["product.product"].create({
            "name": "Verwijderen van de dakdoorvoer", "default_code": "S99053",
            "type": "service", "list_price": 16.85,
        })

    def _html(self, report, records):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(report, records.ids)
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_quotation_without_reference(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.product.id})],
        })
        self.assertIn("[S99053]", order.order_line.label, "Odoo's label carries it")
        html = self._html("sale.action_report_saleorder", order)
        self.assertIn("Verwijderen van de dakdoorvoer", html)
        self.assertNotIn("[S99053]", html)

    def test_invoice_without_reference(self):
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.product.id, "price_unit": 16.85})],
        })
        html = self._html("account.account_invoices", invoice)
        self.assertIn("Verwijderen van de dakdoorvoer", html)
        self.assertNotIn("[S99053]", html)
