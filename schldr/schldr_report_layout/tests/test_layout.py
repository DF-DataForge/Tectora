# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSchldrLayout(TransactionCase):

    def setUp(self):
        super().setUp()
        self.view = self.env.ref("schldr_report_layout.external_layout_schldr")
        self.layout = self.env.ref("schldr_report_layout.report_layout_schldr")
        self.company = self.env.company

    def test_layout_is_a_configurator_choice(self):
        self.assertEqual(self.layout.view_id, self.view)
        self.assertIn(self.layout, self.env["report.layout"].search([]))
        self.assertEqual(self.view.key, "schldr_report_layout.external_layout_schldr")

    def test_install_switches_companies(self):
        self.assertEqual(self.company.external_report_layout_id, self.view)
        self.assertTrue(self.company.primary_color)

    def test_wizard_preview_renders_the_layout(self):
        wizard = self.env["base.document.layout"].create({"company_id": self.company.id})
        wizard.report_layout_id = self.layout
        wizard._onchange_report_layout_id()
        self.assertEqual(wizard.external_report_layout_id, self.view)
        preview = wizard.preview
        self.assertIn("o_report_layout_schldr", preview)
        self.assertIn("o_schldr_header_shape", preview)
        self.assertIn(wizard.primary_color.lower(), preview.lower(), "the accent edge takes the primary colour")

    def test_external_report_uses_the_layout(self):
        self.company.write({"external_report_layout_id": self.view.id, "primary_color": "#2F5D8A"})
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        html = html.decode() if isinstance(html, bytes) else str(html)
        self.assertIn("o_report_layout_schldr", html)
        self.assertIn("#2F5D8A", html)
        self.assertIn("o_schldr_footer", html)

    def test_schldr_table_design(self):
        """"Schldr" is a table design of its own, for any layout; another
        design on a Schldr layout is honoured."""
        selection = dict(self.env["res.company"]._fields["report_tables_id"].selection)
        self.assertIn("schldr", selection)
        self.company.write({
            "external_report_layout_id": self.view.id,
            "report_tables_id": "schldr",
            "primary_color": "#2F5D8A",
        })
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        self.assertIn("o_table_schldr", str(html))
        scss = str(self.env["ir.qweb"]._render("web.styles_company_report", {"company_ids": self.company}))
        self.assertIn(".o_table_schldr", scss)

        self.company.report_tables_id = "bold"
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        self.assertIn("o_table_bold", str(html))
        self.assertNotIn("o_table_schldr", str(html))

        # Any layout can take the Schldr tables.
        self.company.write({
            "external_report_layout_id": self.env.ref("web.external_layout_standard").id,
            "report_tables_id": "schldr",
        })
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "web.preview_externalreport", [self.company.id]
        )
        self.assertIn("o_table_schldr", str(html))

    def test_company_styles_carry_the_layout_rules(self):
        self.company.write({"external_report_layout_id": self.view.id, "primary_color": "#2F5D8A"})
        scss = self.env["ir.qweb"]._render("web.styles_company_report", {"company_ids": self.company})
        self.assertIn(".o_schldr_footer", str(scss))
        self.assertIn("#2F5D8A", str(scss))


@tagged("post_install", "-at_install")
class TestSchldrLetterhead(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.write({
            "name": "Schldr BV",
            "street": "Vuurkruiserslaan 28",
            "zip": "8870",
            "city": "Izegem",
            "vat": "BE1031956670",
            "email": "info@schldr.be",
            "phone": "0472 09 20 98",
            "website": "https://www.schldr.be",
            "primary_color": "#3A6A99",
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
            "report_layout_schldr_letterhead",
            "report_layout_schldr_letterhead_light",
            "report_layout_schldr_accent_letterhead",
        ):
            self.assertIn(self.env.ref("schldr_report_layout." + xmlid), layouts)

    def test_footer_lines(self):
        self.env["res.partner.bank"].create({
            "partner_id": self.company.partner_id.id,
            "account_number": "BE62739028873261",
            "bank_name": "KBC",
        })
        lines = self.company._schldr_letterhead_footer_lines()
        self.assertEqual(
            lines["identity"], "Schldr BV — Vuurkruiserslaan 28, 8870 Izegem — BE 1031.956.670"
        )
        self.assertEqual(lines["contact"], "info@schldr.be — 0472 09 20 98")
        self.assertEqual(lines["banks"], "KBC BE62 7390 2887 3261")
        self.assertEqual(self.company._schldr_letterhead_website(), "www.schldr.be")

    def test_letterhead_renders(self):
        html = self._render("schldr_report_layout.external_layout_schldr_letterhead")
        self.assertIn("o_schldr_lh_header", html)
        self.assertIn("schldr_logo_white.svg", html)
        self.assertIn("www.schldr.be", html)
        self.assertIn("BE 1031.956.670", html)
        self.assertIn("#3A6A99", html)
        self.assertIn("o_report_layout_schldr", html)

    def test_light_letterhead_renders(self):
        html = self._render("schldr_report_layout.external_layout_schldr_letterhead_light")
        self.assertIn("o_schldr_lh_light", html)
        self.assertIn("schldr_logo.svg", html)
        self.assertNotIn("schldr_logo_white.svg", html)
        self.assertIn("o_schldr_lh_footer_inverse", html)
        self.assertIn("background-color: #3A6A99;", html)

    def test_sender_block(self):
        sender = self.company._schldr_letterhead_sender()
        self.assertEqual(sender["name"], "Schldr BV")
        self.assertEqual(sender["address"], ["Vuurkruiserslaan 28", "8870 Izegem"])
        self.assertEqual(sender["contacts"], [
            ("Telefoon", "0472 09 20 98"),
            ("E-mail", "info@schldr.be"),
            ("Website", "www.schldr.be"),
        ])
        self.assertEqual(self.company._schldr_letterhead_site(), [])

    def test_accent_letterhead_renders(self):
        html = self._render("schldr_report_layout.external_layout_schldr_accent_letterhead")
        self.assertIn("o_schldr_parties", html)
        self.assertIn("Vuurkruiserslaan 28", html)
        self.assertIn("o_schldr_rlh_shape", html)
        self.assertIn("o_schldr_lh_footer", html)
        self.assertIn("schldr_logo_white.svg", html)

    def test_configurator_previews_the_letterheads(self):
        # The preview renders the layout with the configurator itself as
        # `company`: the letterhead takes the address from the company it
        # configures.
        for xmlid in (
            "report_layout_schldr_letterhead",
            "report_layout_schldr_letterhead_light",
            "report_layout_schldr_accent_letterhead",
        ):
            wizard = self.env["base.document.layout"].create({"company_id": self.company.id})
            wizard.report_layout_id = self.env.ref("schldr_report_layout." + xmlid)
            wizard._onchange_report_layout_id()
            preview = wizard.preview
            self.assertIn("o_schldr_lh_footer", preview)
            self.assertIn("Vuurkruiserslaan 28, 8870 Izegem", preview)
            self.assertIn("www.schldr.be", preview)

    def test_company_styles_cover_the_letterheads(self):
        view = self.env.ref("schldr_report_layout.external_layout_schldr_letterhead")
        self.company.external_report_layout_id = view
        scss = self.env["ir.qweb"]._render("web.styles_company_report", {"company_ids": self.company})
        self.assertIn(".o_schldr_footer", str(scss))
