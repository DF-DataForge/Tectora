# -*- coding: utf-8 -*-
"""Terms and conditions added as a PDF: not in the note of quotations and
invoices, but on pages of their own at the end of their PDF."""
from odoo.tests import TransactionCase, tagged

TERMS = "<p>Artikel 1. Toepassingsgebied</p>"


@tagged("post_install", "-at_install")
class TestTermsPdf(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env["ir.config_parameter"].sudo().set_bool("account.use_invoice_terms", True)
        cls.company = cls.env.company
        cls.company.write({"terms_type": "pdf", "invoice_terms": TERMS})
        cls.partner = cls.env["res.partner"].create({"name": "Klant"})
        cls.product = cls.env["product.product"].create({"name": "Werk", "list_price": 100})

    def _order(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1})],
        })

    def _html(self, report, records):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(report, records.ids)
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_option_exists(self):
        selection = dict(self.env["res.company"]._fields["terms_type"].selection)
        self.assertIn("pdf", selection)

    def test_quotation_note_stays_empty(self):
        self.assertFalse(self._order().note)

    def test_quotation_pdf_has_terms_page(self):
        order = self._order()
        for standard in (True, False):
            order.tectora_standard_quotation = standard
            html = self._html("sale.action_report_saleorder", order)
            self.assertIn("o_tectora_terms", html)
            self.assertIn("Artikel 1. Toepassingsgebied", html)
            self.assertIn("Algemene voorwaarden", html)

    def test_invoice_has_terms_page_not_note(self):
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.product.id, "price_unit": 100})],
        })
        self.assertFalse(invoice.narration)
        html = self._html("account.account_invoices", invoice)
        self.assertIn("o_tectora_terms", html)
        self.assertIn("Artikel 1. Toepassingsgebied", html)

    def test_as_text_keeps_the_note(self):
        self.company.terms_type = "plain"
        order = self._order()
        self.assertIn("Artikel 1", order.note)
        html = self._html("sale.action_report_saleorder", order)
        self.assertNotIn("o_tectora_terms", html)
