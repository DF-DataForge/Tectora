# -*- coding: utf-8 -*-
"""The site address of a roof project is a contact: the delivery address of
its order, kept equal both ways."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSiteAddress(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Partner = cls.env["res.partner"]
        cls.customer = Partner.create({
            "name": "Data Forge", "street": "Kerkstraat 1", "zip": "8500", "city": "Kortrijk",
        })
        cls.site = Partner.create({
            "name": "Werf Wortegem", "parent_id": cls.customer.id, "type": "delivery",
            "street": "Waregemseweg 32", "zip": "9790", "city": "Wortegem",
        })
        cls.other_site = Partner.create({
            "name": "Werf Heule", "parent_id": cls.customer.id, "type": "delivery",
            "street": "Mellestraat 358", "zip": "8501", "city": "Heule",
        })

    def test_order_and_roof_share_the_site(self):
        # A quotation makes its roof project, the delivery address its site.
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "partner_shipping_id": self.site.id,
        })
        roof = order.roof_project_id
        self.assertTrue(roof)
        self.assertEqual(roof.site_partner_id, self.site)
        self.assertIn("Waregemseweg 32", roof.address)
        self.assertIn("Wortegem", roof.address)

        # Another site on the roof project: the order's delivery address.
        roof.site_partner_id = self.other_site
        self.assertEqual(order.partner_shipping_id, self.other_site)
        self.assertIn("Heule", roof.address)

        # And the other way round.
        order.partner_shipping_id = self.site
        self.assertEqual(roof.site_partner_id, self.site)

    def test_new_roof_project_takes_the_customer(self):
        roof = self.env["tectora.roof.project"].create({
            "name": "Dak", "partner_id": self.customer.id,
        })
        self.assertEqual(roof.site_partner_id, self.customer)
        self.assertIn("Kortrijk", roof.address)
