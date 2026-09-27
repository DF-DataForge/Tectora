# -*- coding: utf-8 -*-
"""The whole flow of a site, from the roof project to the invoice, and every
printed document on the way.

Confirming an order builds its dossier inside a savepoint that logs and
swallows errors (a failing dossier must not block the sale), so an API change
there shows only as an empty material list: this test is what notices it.
"""
import base64
import io

from PIL import Image

from odoo import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_roof.models.sale_order import QUOTATION_STYLES


@tagged("post_install", "-at_install")
class TestEndToEnd(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        unit = env.ref("uom.product_uom_unit")
        cls.vendor = env["res.partner"].create({"name": "Dakhandel NV", "supplier_rank": 1})
        Product = env["product.product"]
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "is_storable": True,
            "uom_id": m2.id, "standard_price": 9.0,
            "seller_ids": [Command.create({"partner_id": cls.vendor.id, "price": 8.5})],
        })
        cls.glue = Product.create({
            "name": "Contactlijm", "type": "consu", "uom_id": unit.id,
            "standard_price": 4.0,
            "seller_ids": [Command.create({"partner_id": cls.vendor.id, "price": 3.9})],
        })
        cls.works = Product.create({
            "name": "Dakbedekking EPDM", "type": "service", "uom_id": m2.id,
            "list_price": 45.0,
            "tectora_hours_execution_per_uom": 0.2,
            "tectora_hours_demolition_per_uom": 0.1,
        })
        env["mrp.bom"].create({
            "product_tmpl_id": cls.works.product_tmpl_id.id,
            "type": "phantom",
            "uom_id": m2.id,
            "bom_line_ids": [
                Command.create({"product_id": cls.epdm.id, "product_qty": 1.1}),
                Command.create({"product_id": cls.glue.id, "product_qty": 0.2}),
            ],
        })
        cls.customer = env["res.partner"].create({
            "name": "Familie Peeters", "street": "Kerkstraat 12", "zip": "2000",
            "city": "Antwerpen", "country_id": env.ref("base.be").id,
        })
        cls.roof = env["tectora.roof.project"].create(
            {"name": "Plat dak Peeters", "partner_id": cls.customer.id}
        )
        env["tectora.roof.section"].create({
            "project_id": cls.roof.id, "name": "Hoofddak", "area": 100.0, "perimeter": 40.0,
        })
        env["tectora.roof.section.product"].create(
            {"project_direct_id": cls.roof.id, "product_id": cls.works.id}
        )
        cls.roof.action_create_sale_order()
        cls.order = cls.roof.sale_order_id

    def render(self, report, records, needle=None):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(report, records.ids)
        html = html.decode() if isinstance(html, bytes) else str(html)
        self.assertGreater(len(html), 2000, report)
        if needle:
            self.assertIn(needle, html, report)
        return html

    def test_site_to_invoice(self):
        # A chapter heading and the works item, measured from the drawing.
        line = self.order.order_line.filtered(lambda l: not l.display_type)
        self.assertEqual(line.product_id, self.works)
        self.assertAlmostEqual(line.product_uom_qty, 100.0)

        self.order.action_confirm()
        materials = {m.product_id: m.quantity for m in self.roof.material_line_ids}
        self.assertAlmostEqual(materials[self.epdm], 110.0)
        self.assertAlmostEqual(materials[self.glue], 20.0)
        project = self.roof.project_id
        self.assertTrue(project, "confirming builds the project")
        self.assertEqual(
            set(project.task_ids.mapped("name")), {"Afbraakwerken", "Uitvoeringswerken"}
        )
        self.assertEqual(set(self.roof.material_line_ids.vendor_id), {self.vendor})

        action = self.roof.action_create_material_picking()
        picking = self.env["stock.picking"].browse(action["res_id"])
        self.assertEqual(set(picking.move_ids.product_id), {self.epdm, self.glue})

        wizard = self.env["tectora.purchase.from.material"].create({
            "material_line_ids": [Command.set(self.roof.material_line_ids.ids)],
            "confirm": True,
        })
        wizard.action_create_purchase_orders()
        purchase = self.roof.material_line_ids.purchase_line_id.order_id
        self.assertEqual(purchase.partner_id, self.vendor)
        self.assertEqual(purchase.state, "purchase")
        line = purchase.order_line.filtered(lambda l: l.product_id == self.epdm)
        self.assertAlmostEqual(line.price_unit, 8.5, msg="the vendor price")

        invoice = self.order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

        self.render("purchase.action_report_purchase_order", purchase, "EPDM")
        self.render("account.account_invoices", invoice, "Peeters")

        # The project dashboard: what was invoiced, and the ordered material
        # as cost still to be billed (Odoo 20 dropped the profitability API
        # these figures came from).
        project.invalidate_recordset()
        self.assertAlmostEqual(project.tectora_invoiced, self.order.amount_untaxed)
        self.assertAlmostEqual(project.tectora_to_invoice, 0.0)
        self.assertAlmostEqual(project.tectora_cost_to_bill, purchase.amount_untaxed, places=2)
        self.assertAlmostEqual(
            project.tectora_margin, self.order.amount_untaxed - project.tectora_costs, places=2
        )

    def test_drawing_reaches_the_documents(self):
        """The drawing is a PNG in the measurement sheet and the quotation,
        whether it is the canvas snapshot or the server-side fallback render
        (binary fields hold raw bytes since Odoo 20, no longer base64)."""
        buffer = io.BytesIO()
        Image.new("RGB", (40, 30), (10, 116, 131)).save(buffer, format="PNG")
        png = buffer.getvalue()
        self.assertEqual(self.roof._get_drawing_png()[:8], b"\x89PNG\r\n\x1a\n", "fallback render")
        self.roof.canvas_snapshot = base64.b64encode(png).decode()
        self.assertEqual(self.roof._get_drawing_png(), png)
        data_uri = "data:image/png;base64," + base64.b64encode(png).decode()
        self.render("tectora_roof.report_roof_project", self.roof, data_uri)
        self.order.write({"tectora_standard_quotation": False, "tectora_quotation_style": "dossier"})
        self.render("sale.action_report_saleorder", self.order, data_uri)

    def test_every_document_renders(self):
        for style, _label in QUOTATION_STYLES:
            self.order.write({"tectora_standard_quotation": False, "tectora_quotation_style": style})
            self.render("sale.action_report_saleorder", self.order, "Peeters")
        self.order.tectora_standard_quotation = True
        self.render("sale.action_report_saleorder", self.order, "Peeters")
        for report in (
            "tectora_roof.report_roof_project",
            "tectora_roof.report_roof_project_info",
            "tectora_purchase.report_logistics_lists",
            "tectora_purchase.report_logistics_stock",
            "tectora_purchase.report_logistics_warehouse",
            "tectora_purchase.report_logistics_dropship",
        ):
            self.render(report, self.roof)
