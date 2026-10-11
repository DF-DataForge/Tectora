# -*- coding: utf-8 -*-
"""The transport order ("Bestelbon materialen") of a roof project's purchase
order: built from the site information, and mailed with the order."""
import base64
import io

from PIL import Image

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTransportOrder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        cls.vendor = env["res.partner"].create({"name": "Modde", "supplier_rank": 1})
        cls.customer = env["res.partner"].create({"name": "Descheemaker-Devos"})
        cls.epdm = env["product.product"].create({
            "name": "Elevate EPDM folie 1,10mm", "type": "consu", "default_code": "P00444",
        })
        buffer = io.BytesIO()
        Image.new("RGB", (40, 30), (10, 116, 131)).save(buffer, format="PNG")
        cls.roof = env["tectora.roof.project"].create({
            "name": "Plat dak garages", "partner_id": cls.customer.id,
            "address": "Koningin Astridlaan zn, 8870 Emelgem",
            "roof_height": 3.0,
            "roof_access_crane": "levering op het dak",
            "material_direct_roof": True,
            "site_photo_top": base64.b64encode(buffer.getvalue()).decode(),
        })
        cls.order = env["purchase.order"].create({
            "partner_id": cls.vendor.id,
            "partner_ref": "O-1234",
            "tectora_roof_project_id": cls.roof.id,
            "order_line": [Command.create({"product_id": cls.epdm.id, "product_qty": 3})],
        })

    def test_report_content(self):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "tectora_purchase.action_report_transport_order", self.order.ids
        )
        html = html.decode() if isinstance(html, bytes) else str(html)
        for needle in (
            "Bestelbon materialen", "Modde", "O-1234", "Descheemaker-Devos",
            "Koningin Astridlaan zn", "3,00 m", "levering op het dak",
            "Bovenaanzicht", "data:image/png;base64", "Elevate EPDM folie 1,10mm",
            "Op te halen in loods",
        ):
            self.assertIn(needle, html)
        self.assertNotIn("Gevelaanzicht", html, "no photo, no caption")
        self.assertEqual(
            self.order._tectora_transport_order_lines(),
            [{"name": "Elevate EPDM folie 1,10mm", "qty": 3.0, "uom": self.epdm.uom_id.name}],
        )

    def test_mailed_with_the_order(self):
        template = self.env.ref("purchase.email_template_edi_purchase_done")
        attachments = self.order._process_attachments_for_template_post(template)
        names = [name for name, _content in attachments[self.order.id]["attachments"]]
        self.assertEqual(names, ["Bestelbon materialen - %s.pdf" % self.order.name.replace("/", "-")])

    def test_not_for_orders_without_project(self):
        order = self.env["purchase.order"].create({"partner_id": self.vendor.id})
        template = self.env.ref("purchase.email_template_edi_purchase_done")
        self.assertFalse(order._process_attachments_for_template_post(template).get(order.id))
