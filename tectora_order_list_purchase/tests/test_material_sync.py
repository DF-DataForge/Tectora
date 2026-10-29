# -*- coding: utf-8 -*-
"""What the order list orders or takes from stock shows on the material list."""
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMaterialSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        env["tectora.order.list.template"].search([]).action_archive()
        m2 = env.ref("uom.product_uom_square_meter")
        unit = env.ref("uom.product_uom_unit")
        cls.vendor_1 = env["res.partner"].create({"name": "Dakhandel NV", "supplier_rank": 1})
        cls.vendor_2 = env["res.partner"].create({"name": "Isolatie BV", "supplier_rank": 1})
        Product = env["product.product"]
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "is_storable": True, "purchase_ok": True,
            "uom_id": m2.id, "standard_price": 9.0,
            "seller_ids": [Command.create({"partner_id": cls.vendor_1.id, "price": 8.5})],
        })
        cls.glue = Product.create({
            "name": "Contactlijm", "type": "consu", "is_storable": True, "purchase_ok": True,
            "uom_id": unit.id, "standard_price": 4.0,
            "seller_ids": [Command.create({"partner_id": cls.vendor_2.id, "price": 3.9})],
        })
        cls.works = Product.create({
            "name": "Dakbedekking EPDM", "type": "service", "uom_id": m2.id, "list_price": 45.0,
        })
        env["mrp.bom"].create({
            "product_tmpl_id": cls.works.product_tmpl_id.id,
            "type": "phantom",
            "uom_id": m2.id,
            "bom_line_ids": [
                Command.create({"product_id": cls.epdm.id, "product_qty": 1.1}),
                Command.create({"product_id": cls.glue.id, "product_qty": 0.05}),
            ],
        })
        env["tectora.order.list.template"].create({
            "name": "Materiaal", "sequence": 1, "order_action": "order",
            "partner_ids": [(6, 0, (cls.vendor_1 | cls.vendor_2).ids)],
        })
        warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        env["stock.quant"]._update_available_quantity(cls.glue, warehouse.lot_stock_id, 20)
        customer = env["res.partner"].create({"name": "Bouwbedrijf Claes", "city": "Kortrijk"})
        cls.order = env["sale.order"].create({
            "partner_id": customer.id,
            "order_line": [Command.create({"product_id": cls.works.id, "product_uom_qty": 100})],
        })
        cls.order.action_confirm()
        cls.roof = cls.order.roof_project_id
        cls.project = cls.roof.project_id
        cls.part = cls.project.tectora_order_line_ids

    def _material(self, product):
        return self.env["tectora.roof.material"].search([
            ("project_id", "=", self.roof.id), ("product_id", "=", product.id),
        ])

    def test_material_list_is_built(self):
        self.assertEqual(len(self.part), 1)
        self.assertEqual(self._material(self.epdm).purchase_state, "to_order")
        self.assertEqual(self._material(self.glue).purchase_state, "to_order")

    def test_order_on_order_list_shows_on_material_list(self):
        self.part.partner_id = self.vendor_1
        action = self.part.action_tectora_create_purchase(
            [{"product_id": self.epdm.id, "quantity": 110}]
        )
        order = self.env["purchase.order"].browse(action["res_id"])
        material = self._material(self.epdm)
        self.assertEqual(material.purchase_order_id, order)
        self.assertEqual(material.vendor_id, self.vendor_1)
        self.assertEqual(material.purchase_state, "rfq")
        order.button_confirm()
        self.assertEqual(material.purchase_state, "ordered")
        self.assertEqual(self._material(self.glue).purchase_state, "to_order",
                         "a product that was not ordered stays to order")

    def test_delivery_from_stock_shows_on_material_list(self):
        self.part.action_tectora_deliver_from_stock(
            [{"product_id": self.glue.id, "quantity": 5}]
        )
        material = self._material(self.glue)
        self.assertEqual(material.purchase_state, "stock")
        self.assertTrue(material.picking_id)
        self.assertEqual(material.picking_id.origin, f"{self.project.name} · Bestellijst")
        material.order_list_move_id.picking_id.action_cancel()
        self.assertEqual(material.purchase_state, "to_order",
                         "a cancelled delivery puts the material back to order")

    def test_existing_purchase_order_is_kept(self):
        material = self._material(self.epdm)
        own = self.env["purchase.order"].create({
            "partner_id": self.vendor_2.id,
            "order_line": [Command.create({"product_id": self.epdm.id, "product_qty": 110})],
        })
        material.purchase_line_id = own.order_line
        self.part.partner_id = self.vendor_1
        self.part.action_tectora_create_purchase([{"product_id": self.epdm.id, "quantity": 110}])
        self.assertEqual(material.purchase_order_id, own)
