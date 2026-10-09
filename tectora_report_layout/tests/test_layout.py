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


@tagged("post_install", "-at_install")
class TestTectoraLetterhead(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.write({
            "name": "Tectora BV",
            "street": "Vuurkruiserslaan 28",
            "zip": "8870",
            "city": "Izegem",
            "vat": "BE1031956670",
            "email": "info@tectora.be",
            "phone": "0472 09 20 98",
            "website": "https://www.tectora.be",
            "primary_color": "#2D8D8F",
        })

    def _render(self, xmlid):
        view = self.env.ref(xmlid)
        self.company.external_report_layout_id = view
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_layouts_are_configurator_choices(self):
        layouts = self.env["report.layout"].search([])
        for xmlid in (
            "report_layout_tectora_letterhead",
            "report_layout_tectora_letterhead_light",
            "report_layout_tectora_roof_letterhead",
        ):
            self.assertIn(self.env.ref("tectora_report_layout." + xmlid), layouts)

    def test_footer_lines(self):
        self.env["res.partner.bank"].create({
            "partner_id": self.company.partner_id.id,
            "account_number": "BE62739028873261",
            "bank_name": "KBC",
        })
        lines = self.company._tectora_letterhead_footer_lines()
        self.assertEqual(
            lines["identity"], "Tectora BV — Vuurkruiserslaan 28, 8870 Izegem — BE 1031.956.670"
        )
        self.assertEqual(lines["contact"], "info@tectora.be — 0472 09 20 98")
        self.assertEqual(lines["banks"], "KBC BE62 7390 2887 3261")
        self.assertEqual(self.company._tectora_letterhead_website(), "www.tectora.be")

    def test_letterhead_renders(self):
        html = self._render("tectora_report_layout.external_layout_tectora_letterhead")
        self.assertIn("o_tectora_lh_header", html)
        self.assertIn("tectora_logo_white.svg", html)
        self.assertIn("www.tectora.be", html)
        self.assertIn("BE 1031.956.670", html)
        self.assertIn("#2D8D8F", html)
        self.assertIn("o_report_layout_tectora", html)

    def test_light_letterhead_renders(self):
        html = self._render("tectora_report_layout.external_layout_tectora_letterhead_light")
        self.assertIn("o_tectora_lh_light", html)
        self.assertIn("tectora_logo.svg", html)
        self.assertNotIn("tectora_logo_white.svg", html)
        self.assertIn("o_tectora_lh_footer_inverse", html)
        self.assertIn("background-color: #2D8D8F;", html)

    def test_roof_letterhead_renders(self):
        html = self._render("tectora_report_layout.external_layout_tectora_roof_letterhead")
        self.assertIn("o_tectora_rlh_shape", html)
        self.assertIn("o_tectora_lh_footer", html)
        self.assertIn("tectora_logo_white.svg", html)

    def test_company_styles_cover_the_letterheads(self):
        view = self.env.ref("tectora_report_layout.external_layout_tectora_letterhead")
        self.company.external_report_layout_id = view
        scss = self.env["ir.qweb"]._render("web.styles_company_report", {"company_ids": self.company})
        self.assertIn(".o_report_layout_tectora", str(scss))
