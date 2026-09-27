# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTectoraLayout(TransactionCase):

    def setUp(self):
        super().setUp()
        self.view = self.env.ref("tectora_report_layout.external_layout_tectora")
        self.layout = self.env.ref("tectora_report_layout.report_layout_tectora")
        self.company = self.env.company

    def test_layout_is_a_configurator_choice(self):
        self.assertEqual(self.layout.view_id, self.view)
        self.assertIn(self.layout, self.env["report.layout"].search([]))
        self.assertEqual(self.view.key, "tectora_report_layout.external_layout_tectora")

    def test_install_switches_companies(self):
        self.assertEqual(self.company.external_report_layout_id, self.view)
        self.assertTrue(self.company.primary_color)

    def test_wizard_preview_renders_the_layout(self):
        wizard = self.env["base.document.layout"].create({"company_id": self.company.id})
        wizard.report_layout_id = self.layout
        wizard._onchange_report_layout_id()
        self.assertEqual(wizard.external_report_layout_id, self.view)
        preview = wizard.preview
        self.assertIn("o_report_layout_tectora", preview)
        self.assertIn("o_tectora_header_shape", preview)
        self.assertIn(wizard.primary_color.lower(), preview.lower(), "the roof edge takes the primary colour")

    def test_external_report_uses_the_layout(self):
        self.company.write({"external_report_layout_id": self.view.id, "primary_color": "#008B93"})
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        html = html.decode() if isinstance(html, bytes) else str(html)
        self.assertIn("o_report_layout_tectora", html)
        self.assertIn("#008B93", html)
        self.assertIn("o_tectora_footer", html)

    def test_company_styles_carry_the_layout_rules(self):
        self.company.write({"external_report_layout_id": self.view.id, "primary_color": "#008B93"})
        scss = self.env["ir.qweb"]._render("web.styles_company_report", {"company_ids": self.company})
        self.assertIn(".o_report_layout_tectora", str(scss))
        self.assertIn("#008B93", str(scss))
