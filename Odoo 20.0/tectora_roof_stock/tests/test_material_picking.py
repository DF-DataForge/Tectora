# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMaterialPicking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Dakklant"})
        cls.epdm = cls.env["product.product"].create({
            "name": "EPDM 1,1 mm", "type": "consu", "is_storable": True,
            "uom_id": cls.env.ref("uom.product_uom_square_meter").id,
        })
        cls.primer = cls.env["product.product"].create({
            "name": "QuickPrime", "type": "consu", "is_storable": True,
        })
        cls.labour = cls.env["product.product"].create({
            "name": "Werkuren", "type": "service",
        })
        cls.project = cls.env["tectora.roof.project"].with_context(
            tectora_sync=True
        ).create({"name": "Werf test", "partner_id": cls.customer.id})
        Material = cls.env["tectora.roof.material"]
        # The same primer twice, from two works items: one move, added up.
        Material.create([
            {"project_id": cls.project.id, "product_id": cls.epdm.id, "quantity": 110.0,
             "product_uom_id": cls.epdm.uom_id.id},
            {"project_id": cls.project.id, "product_id": cls.primer.id, "quantity": 0.3,
             "product_uom_id": cls.primer.uom_id.id},
            {"project_id": cls.project.id, "product_id": cls.primer.id, "quantity": 0.5,
             "product_uom_id": cls.primer.uom_id.id},
            {"project_id": cls.project.id, "product_id": cls.labour.id, "quantity": 12.0,
             "product_uom_id": cls.labour.uom_id.id},
        ])

    def test_picking_from_material_list(self):
        action = self.project.action_create_material_picking()
        picking = self.env["stock.picking"].browse(action["res_id"])
        self.assertEqual(picking.tectora_roof_project_id, self.project)
        self.assertEqual(picking.picking_type_id.code, "outgoing")
        self.assertEqual(picking.partner_id, self.customer)
        self.assertNotEqual(picking.state, "draft", "confirmed for the warehouse")
        by_product = {move.product_id: move.product_uom_qty for move in picking.move_ids}
        self.assertEqual(set(by_product), {self.epdm, self.primer}, "labour does not move")
        self.assertAlmostEqual(by_product[self.epdm], 110.0)
        self.assertAlmostEqual(by_product[self.primer], 0.8, places=3)
        self.assertIn(picking, self.project._get_pickings())
        self.assertEqual(self.project.material_picking_count, 1)
        # Everything is on a transfer: nothing left to ship.
        with self.assertRaises(UserError):
            self.project.action_create_material_picking()

    def test_second_picking_ships_the_difference(self):
        self.project.action_create_material_picking()
        # A change order: 20 m2 more EPDM and a new material.
        self.env["tectora.roof.material"].create([
            {"project_id": self.project.id, "product_id": self.epdm.id, "quantity": 20.0,
             "product_uom_id": self.epdm.uom_id.id},
        ])
        action = self.project.action_create_material_picking()
        second = self.env["stock.picking"].browse(action["res_id"])
        self.assertEqual(len(second.move_ids), 1)
        self.assertEqual(second.move_ids.product_id, self.epdm)
        self.assertAlmostEqual(second.move_ids.product_uom_qty, 20.0)
        self.assertEqual(self.project.material_picking_count, 2)

    def test_cancelled_picking_does_not_count(self):
        action = self.project.action_create_material_picking()
        first = self.env["stock.picking"].browse(action["res_id"])
        first.action_cancel()
        action = self.project.action_create_material_picking()
        again = self.env["stock.picking"].browse(action["res_id"])
        self.assertAlmostEqual(
            sum(again.move_ids.filtered(lambda m: m.product_id == self.epdm).mapped("product_uom_qty")),
            110.0,
        )
        self.assertEqual(self.project.material_picking_count, 1)

    def test_no_goods_no_picking(self):
        empty = self.env["tectora.roof.project"].with_context(tectora_sync=True).create(
            {"name": "Leeg", "partner_id": self.customer.id}
        )
        with self.assertRaises(UserError):
            empty.action_create_material_picking()
