# -*- coding: utf-8 -*-
"""Quantities and products stay equal between the roof project and its open
quotation, in both directions, and edited quantities are kept."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLineSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        meter = env.ref("uom.product_uom_meter")
        unit = env.ref("uom.product_uom_unit")
        cls.categ_buildup = env["product.category"].create({"name": "Opbouw"})
        cls.categ_demolition = env["product.category"].create({"name": "Afbraak"})
        Product = env["product.product"]
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "uom_id": m2.id,
            "categ_id": cls.categ_buildup.id, "list_price": 30,
        })
        cls.epdm_thick = Product.create({
            "name": "EPDM 2 mm", "type": "consu", "uom_id": m2.id,
            "categ_id": cls.categ_buildup.id, "list_price": 40,
        })
        cls.trim = Product.create({
            "name": "Daktrim", "type": "consu", "uom_id": meter.id,
            "categ_id": cls.categ_buildup.id, "list_price": 12,
        })
        cls.container = Product.create({
            "name": "Container", "type": "consu", "uom_id": unit.id,
            "categ_id": cls.categ_demolition.id, "list_price": 250,
        })
        cls.skip = Product.create({
            "name": "Afvoer asbest", "type": "consu", "uom_id": unit.id,
            "categ_id": cls.categ_demolition.id, "list_price": 400,
        })
        cls.partner = env["res.partner"].create({"name": "Klant Sync"})
        cls.project = env["tectora.roof.project"].create({
            "name": "Sync dak", "partner_id": cls.partner.id,
        })
        cls.section = env["tectora.roof.section"].create({
            "project_id": cls.project.id, "name": "Hoofddak",
            "area": 100.0, "perimeter": 40.0,
        })
        Line = env["tectora.roof.section.product"]
        cls.line_epdm = Line.create({"project_direct_id": cls.project.id, "product_id": cls.epdm.id})
        cls.line_trim = Line.create({"project_direct_id": cls.project.id, "product_id": cls.trim.id})
        cls.line_container = Line.create({"project_direct_id": cls.project.id, "product_id": cls.container.id})
        cls.project.action_create_sale_order()
        cls.order = cls.project.sale_order_id

    def order_line(self, roof_line):
        return self.order.order_line.filtered(lambda line: line.roof_line_id == roof_line)

    def test_initial_mirror(self):
        self.assertTrue(self.order)
        self.assertEqual((self.line_epdm.coverage, self.line_trim.coverage, self.line_container.coverage),
                         ("surface", "edges", "general"))
        self.assertEqual(self.line_epdm.quantity, 100.0)
        self.assertEqual(self.line_trim.quantity, 40.0)
        self.assertEqual(self.line_container.quantity, 1.0)
        for roof_line in (self.line_epdm, self.line_trim, self.line_container):
            line = self.order_line(roof_line)
            self.assertEqual(len(line), 1)
            self.assertEqual(line.product_id, roof_line.product_id)
            self.assertEqual(line.product_uom_qty, roof_line.quantity)

    def test_several_quantity_edits_all_persist(self):
        """Editing one measured quantity after another keeps them all: the
        second edit must not snap the first back to the measurement."""
        line_epdm_thick = self.env["tectora.roof.section.product"].create({
            "project_direct_id": self.project.id, "product_id": self.epdm_thick.id,
        })
        self.line_epdm.quantity = 55.0
        line_epdm_thick.quantity = 66.0
        self.line_container.quantity = 3.0
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.line_epdm.quantity, 55.0)
        self.assertEqual(line_epdm_thick.quantity, 66.0)
        self.assertEqual(self.line_container.quantity, 3.0)
        self.assertEqual(self.order_line(self.line_epdm).product_uom_qty, 55.0)
        self.assertEqual(self.order_line(line_epdm_thick).product_uom_qty, 66.0)
        self.assertEqual(self.order_line(self.line_container).product_uom_qty, 3.0)
        # saving the form sends all edited rows in one write on the project
        self.project.write({"buildup_line_ids": [
            [1, self.line_epdm.id, {"quantity": 57.0}],
            [1, line_epdm_thick.id, {"quantity": 68.0}],
        ]})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.line_epdm.quantity, 57.0)
        self.assertEqual(line_epdm_thick.quantity, 68.0)
        self.assertEqual(self.order_line(self.line_epdm).product_uom_qty, 57.0)

    def test_roof_quantity_to_order(self):
        self.line_container.quantity = 4.0
        self.line_epdm.quantity = 80.0
        self.env.flush_all()
        self.assertEqual(self.order_line(self.line_container).product_uom_qty, 4.0)
        self.assertEqual(self.order_line(self.line_epdm).product_uom_qty, 80.0)

    def test_order_quantity_to_roof(self):
        """A quantity typed on the quotation lands on the roof project, also
        for a measured (m², m) line."""
        self.order_line(self.line_container).write({"product_uom_qty": 5.0})
        self.order_line(self.line_epdm).write({"product_uom_qty": 120.0})
        self.order_line(self.line_trim).write({"product_uom_qty": 45.0})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.line_container.quantity, 5.0)
        self.assertEqual(self.line_epdm.quantity, 120.0)
        self.assertEqual(self.line_trim.quantity, 45.0)
        # and the order keeps what was typed
        self.assertEqual(self.order_line(self.line_epdm).product_uom_qty, 120.0)

    def test_new_order_line_keeps_its_quantity(self):
        line = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": self.epdm_thick.id, "product_uom_qty": 37.0,
        })
        self.env.flush_all()
        self.assertTrue(line.roof_line_id)
        self.assertEqual(line.roof_line_id.project_direct_id, self.project)
        self.assertEqual(line.roof_line_id.coverage, "surface")
        self.assertEqual(line.roof_line_id.quantity, 37.0)
        self.assertEqual(line.product_uom_qty, 37.0)
        self.assertIn(line.roof_line_id, self.project.buildup_line_ids)

    def test_order_without_drawing_keeps_quantities(self):
        """A quotation made in Sales gets its roof project; an m² line on it
        must not be zeroed by a roof without measurement."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        roof = order.roof_project_id
        self.assertTrue(roof)
        self.assertEqual(roof.total_area, 0.0)
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.epdm.id, "product_uom_qty": 12.0,
        })
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(line.product_uom_qty, 12.0)
        self.assertEqual(line.roof_line_id.quantity, 12.0)

    def test_product_change_both_ways(self):
        self.line_container.product_id = self.skip
        self.env.flush_all()
        self.assertEqual(self.order_line(self.line_container).product_id, self.skip)
        order_line = self.order_line(self.line_epdm)
        order_line.write({"product_id": self.epdm_thick.id})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.line_epdm.product_id, self.epdm_thick)
        self.assertEqual(self.line_epdm.coverage, "surface")

    def test_drawing_change_moves_measured_lines_and_order(self):
        self.line_epdm.quantity = 55.0  # a manual figure ...
        self.env.flush_all()
        self.section.write({"area": 150.0, "perimeter": 50.0})  # ... until the drawing changes
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.project.total_area, 150.0)
        self.assertEqual(self.line_epdm.quantity, 150.0)
        self.assertEqual(self.line_trim.quantity, 50.0)
        self.assertEqual(self.line_container.quantity, 1.0)
        self.assertEqual(self.order_line(self.line_epdm).product_uom_qty, 150.0)
        self.assertEqual(self.order_line(self.line_trim).product_uom_qty, 50.0)

    def test_estimated_total_follows_quantities(self):
        self.line_container.quantity = 2.0
        self.env.flush_all()
        self.env.invalidate_all()
        expected = 100 * 30 + 40 * 12 + 2 * 250
        self.assertAlmostEqual(self.project.estimated_total, expected, places=2)

    def test_unlink_both_ways(self):
        container_order_line = self.order_line(self.line_container)
        self.line_container.unlink()
        self.assertFalse(container_order_line.exists())
        trim_line = self.line_trim
        self.order_line(trim_line).unlink()
        self.assertFalse(trim_line.exists())
