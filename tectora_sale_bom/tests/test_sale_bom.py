# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSaleBom(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        unit = env.ref("uom.product_uom_unit")
        Product = env["product.product"]
        cls.roofing = Product.create({
            "name": "Dakbedekking EPDM", "type": "service", "uom_id": m2.id,
            "list_price": 50.0,
        })
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "uom_id": m2.id,
            "standard_price": 10.0,
        })
        cls.glue = Product.create({
            "name": "Lijm", "type": "consu", "uom_id": unit.id, "standard_price": 2.0,
        })
        cls.primer = Product.create({
            "name": "Primer", "type": "consu", "uom_id": unit.id, "standard_price": 5.0,
        })
        cls.container = Product.create({
            "name": "Container", "type": "consu", "uom_id": unit.id,
            "standard_price": 200.0,
        })
        # The shipped demo set: keyed, sequence 0, 10 m2 per BoM.
        cls.demo_bom = env["mrp.bom"].create({
            "product_tmpl_id": cls.roofing.product_tmpl_id.id,
            "product_qty": 10.0,
            "uom_id": m2.id,
            "type": "phantom",
            "sequence": 0,
            "code": "Demo",
            "tectora_bom_key": "demo:TEST",
            "bom_line_ids": [
                Command.create({"product_id": cls.epdm.id, "product_qty": 11.0}),
                Command.create({"product_id": cls.glue.id, "product_qty": 2.0}),
            ],
        })
        cls.partner = env["res.partner"].create({"name": "Klant stuklijst"})
        cls.order = env["sale.order"].create({
            "partner_id": cls.partner.id,
            "order_line": [Command.create({
                "product_id": cls.roofing.id,
                "product_uom_qty": 100.0,
                "price_unit": 50.0,
            })],
        })
        cls.line = cls.order.order_line

    def open_dialog(self, line=None):
        line = line or self.line
        action = line.action_open_tectora_sale_bom()
        Model = self.env["tectora.sale.bom"].with_context(**action.get("context", {}))
        if action.get("res_id"):
            return Form(Model.browse(action["res_id"]), view=action["views"][0][0])
        return Form(Model, view=action["views"][0][0])

    def make_custom(self):
        """Open the dialog, add a primer (0.1 per m2) and a fixed container."""
        with self.open_dialog() as form:
            with form.line_ids.new() as component:
                component.product_id = self.primer
                component.quantity = 0.1
            with form.line_ids.new() as component:
                component.product_id = self.container
                component.quantity = 1.0
                component.fixed_quantity = True
        return self.line.tectora_sale_bom_id

    def materials(self):
        return {
            material.product_id: material.quantity
            for material in self.env["tectora.roof.material"].search(
                [("sale_order_id", "=", self.order.id)]
            )
        }

    def test_dialog_starts_from_default_bom(self):
        form = self.open_dialog()
        self.assertEqual(form.source_bom_id, self.demo_bom)
        self.assertEqual(len(form.line_ids), 2)
        epdm = form.line_ids.edit(0)
        self.assertAlmostEqual(epdm.quantity, 1.1, msg="per m2 of the sold product")
        self.assertAlmostEqual(epdm.total_quantity, 110.0)
        self.assertAlmostEqual(epdm.unit_cost, 10.0)
        epdm.save()
        # 1.1 x 10 + 0.2 x 2 = 11.4 per m2; the margin keeps the line's price.
        self.assertAlmostEqual(form.cost_per_unit, 11.4)
        self.assertAlmostEqual(form.price_computed, 50.0, places=2)
        self.assertFalse(form.price_differs)

    def test_closing_the_dialog_stores_nothing(self):
        self.line.action_open_tectora_sale_bom()
        self.assertFalse(self.env["tectora.sale.bom"].search([("sale_line_id", "=", self.line.id)]))
        self.assertFalse(self.line.tectora_has_sale_bom)

    def test_custom_bom_replaces_product_bom_in_material_list(self):
        custom = self.make_custom()
        self.assertTrue(self.line.tectora_has_sale_bom)
        # The fixed container counts once, spread over the 100 m2.
        self.assertAlmostEqual(custom.cost_total, 1140.0 + 50.0 + 200.0)
        self.assertAlmostEqual(custom.cost_per_unit, 11.4 + 0.5 + 2.0)
        self.order.action_confirm()
        materials = self.materials()
        self.assertAlmostEqual(materials[self.epdm], 110.0)
        self.assertAlmostEqual(materials[self.glue], 20.0)
        self.assertAlmostEqual(materials[self.primer], 10.0)
        self.assertAlmostEqual(materials[self.container], 1.0)

    def test_change_after_confirmation_rebuilds_material_list(self):
        self.order.action_confirm()
        self.assertNotIn(self.primer, self.materials())
        self.make_custom()
        self.assertAlmostEqual(self.materials()[self.primer], 10.0)
        self.line.tectora_sale_bom_id.action_reset()
        self.assertFalse(self.line.tectora_has_sale_bom)
        self.assertNotIn(self.primer, self.materials())
        self.assertAlmostEqual(self.materials()[self.epdm], 110.0)

    def test_apply_price(self):
        custom = self.make_custom()
        self.assertTrue(custom.price_differs)
        custom.action_save_apply_price()
        self.assertAlmostEqual(self.line.price_unit, custom.price_computed, places=2)
        self.assertFalse(custom.price_differs)

    def test_save_as_default_goes_ahead_of_shipped_set(self):
        custom = self.make_custom()
        custom.action_save_as_default()
        saved = custom.source_bom_id
        self.assertNotEqual(saved, self.demo_bom, "the keyed demo BoM is not overwritten")
        self.assertFalse(saved.tectora_bom_key)
        self.assertEqual(saved.code, "Op maat")
        self.assertLess(saved.sequence, self.demo_bom.sequence)
        self.assertEqual(len(self.demo_bom.bom_line_ids), 2)
        found = self.order._tectora_find_boms(self.roofing)[self.roofing]
        self.assertEqual(found, saved, "the saved BoM is the default now")
        by_product = {line.product_id: line for line in saved.bom_line_ids}
        self.assertAlmostEqual(by_product[self.epdm].product_qty, 1.1)
        self.assertTrue(by_product[self.container].tectora_fixed_qty)

        # A second save updates the same BoM instead of piling up new ones.
        custom.line_ids.filtered(lambda l: l.product_id == self.primer).quantity = 0.2
        custom.action_save_as_default()
        self.assertEqual(custom.source_bom_id, saved)
        self.assertEqual(
            self.env["mrp.bom"].search_count([("product_tmpl_id", "=", self.roofing.product_tmpl_id.id)]),
            2,
        )
        self.assertAlmostEqual(
            saved.bom_line_ids.filtered(lambda l: l.product_id == self.primer).product_qty, 0.2
        )

    def test_new_quotation_starts_from_saved_default(self):
        self.make_custom().action_save_as_default()
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({"product_id": self.roofing.id, "product_uom_qty": 20.0})],
        })
        order.action_confirm()
        materials = {
            m.product_id: m.quantity
            for m in self.env["tectora.roof.material"].search([("sale_order_id", "=", order.id)])
        }
        # Fixed on the product's BoM too: one container, not twenty.
        self.assertAlmostEqual(materials[self.container], 1.0)
        self.assertAlmostEqual(materials[self.primer], 2.0)
        self.assertAlmostEqual(materials[self.epdm], 22.0)

    def test_product_without_bom_starts_empty(self):
        labour = self.env["product.product"].create({"name": "Werfinrichting", "type": "service"})
        line = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": labour.id, "product_uom_qty": 1.0,
        })
        with self.open_dialog(line) as form:
            self.assertFalse(form.source_bom_id)
            self.assertEqual(len(form.line_ids), 0)
            with form.line_ids.new() as component:
                component.product_id = self.container
        self.order.action_confirm()
        self.assertAlmostEqual(self.materials()[self.container], 1.0)

    def test_copy_keeps_custom_bom(self):
        self.make_custom()
        copy = self.order.copy()
        copied = copy.order_line.tectora_sale_bom_id
        self.assertTrue(copied)
        self.assertNotEqual(copied, self.line.tectora_sale_bom_id)
        self.assertEqual(len(copied.line_ids), 4)

    def test_cancelled_order_is_read_only(self):
        custom = self.make_custom()
        self.order._action_cancel()
        with self.assertRaises(UserError):
            custom.line_ids[:1].quantity = 5.0

    def test_recalculation_turns_area_into_pieces(self):
        """A component with hercalculatie is counted in m² on the bill of
        materials and comes out in pieces: 1 m² of board per m² of roof,
        boards of 1 m × 0,5 m, 100 m² sold = 200 boards."""
        board = self.env["product.product"].create({
            "name": "Isolatieplaat 1000x500", "type": "consu",
            "uom_id": self.env.ref("uom.product_uom_unit").id,
            "standard_price": 6.0,
            "tectora_recalc": True, "tectora_recalc_uom": "m2",
            "tectora_length": 1.0, "tectora_width": 0.5,
        })
        self.demo_bom.bom_line_ids = [
            Command.create({"product_id": board.id, "product_qty": 10.0}),
        ]
        template = board.product_tmpl_id
        self.assertAlmostEqual(template.tectora_recalc_size, 0.5)
        self.assertEqual(template._tectora_recalculate(10.0), 20.0)
        self.assertEqual(template._tectora_recalculate(10.1), 21.0, "rounded up")
        self.order.action_confirm()
        self.assertEqual(self.materials()[board], 200.0)
        # In the dialog the board costs per m²: 6 per board of 0,5 m².
        form = self.open_dialog()
        component = form.line_ids.edit(2)
        self.assertAlmostEqual(component.unit_cost, 12.0)
