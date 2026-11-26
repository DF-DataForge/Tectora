# -*- coding: utf-8 -*-
"""How a product on the drawing is counted: the measure times a factor, a
fixed number, or a conditional (worst case) item; the terrace floor and the
works on a tapbuis as tick lists."""
import json

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLineQuantities(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        cls.m2 = env.ref("uom.product_uom_square_meter")
        cls.unit = env.ref("uom.product_uom_unit")
        Category = env["product.category"]
        cls.terrace = Category.create({"name": "08. Terrasvloer"})
        cls.worst = Category.create({"name": "09. Worst case scenario"})
        cls.buildup = Category.create({"name": "04. Opbouwwerken plat dak"})
        Product = env["product.product"]

        def product(name, categ, uom, price):
            return Product.create({
                "name": name, "type": "service", "uom_id": uom.id,
                "categ_id": categ.id, "list_price": price, "sale_ok": True,
            })

        cls.supports = product(
            "Leveren en plaatsen van de kunststof tegeldragers regelbaar in hoogte 35-50mm",
            cls.terrace, cls.unit, 5.4)
        cls.tiles = product(
            "Leveren en plaatsen van de volkeramische tegels maat: 60x60cm (dikte: 2cm)",
            cls.terrace, cls.m2, 109.8)
        cls.waste = product("Snijafval tegels 12%", cls.terrace, cls.m2, 60)
        cls.vapour = product(
            "Leveren en plaatsen van het dampscherm klasse E3", cls.buildup, cls.m2, 17.36)
        cls.joints = product("Hervoegen van de naden van alle dekstenen", cls.buildup, cls.unit, 450)
        cls.drain_new = product(
            "Leveren en plaatsen van de PE-tapbuis met zelfklevende slab dia: 90mm",
            cls.buildup, cls.unit, 135)
        cls.drain_guard = product(
            "Leveren en plaatsen van het bolrooster (bladvanger) in de tapbuis dia: 100mm",
            cls.buildup, cls.unit, 8.96)
        # A terrace of 10 x 8 m (0.02 m/px) with a tapbuis on it.
        drawing = {"shapes": [
            {"id": "s", "kind": "section", "name": "Terras",
             "points": [[0, 0], [500, 0], [500, 400], [0, 400]]},
            {"id": "t", "kind": "drain", "name": "Tapbuis 1",
             "points": [[100, 100], [105, 100], [105, 105], [100, 105]]},
        ]}
        cls.project = env["tectora.roof.project"].create({
            "name": "Terras", "partner_id": env["res.partner"].create({"name": "Klant"}).id,
            "scale_m_per_px": 0.02, "canvas_data": json.dumps(drawing),
        })
        cls.project.action_sync_from_canvas()
        cls.section = cls.project.section_ids
        cls.drain = cls.project.roof_object_ids
        cls.Line = env["tectora.roof.section.product"]

    def _line(self, product, **values):
        return self.Line.create(dict({
            "section_id": self.section.id, "product_id": product.id, "coverage": "surface",
        }, **values))

    def test_factor_and_fixed(self):
        self.assertEqual(self.section.area, 80.0)
        self.assertEqual(self.drain.object_type, "drain")
        self.assertEqual(self.section.object_area, 0.0, "a tapbuis takes nothing off the surface")
        supports = self._line(self.supports, quantity_factor=8)
        self.assertEqual(supports.quantity, 640.0, "8 per m2")
        waste = self._line(self.waste, quantity_factor=0.12)
        self.assertAlmostEqual(waste.quantity, 9.6, places=2)
        supports.quantity_factor = 8.3
        self.assertEqual(supports.quantity, 664.0, "pieces are rounded up")
        forfait = self._line(self.joints, quantity_mode="fixed", quantity=1)
        # The surface changes: what follows the measure moves, the forfait stays.
        self.section.area = 100.0
        self.assertEqual(self._line(self.tiles).quantity, 100.0)
        self.assertEqual(supports.quantity, 830.0)
        self.assertEqual(forfait.quantity, 1.0)

    def test_terrace_and_drain_tick_lists(self):
        options = {o["id"]: o for o in self.project.tectora_get_terrace_options()}
        self.assertEqual(options[self.supports.id]["factor"], 8.0)
        self.assertEqual(options[self.waste.id]["factor"], 0.12)
        self.assertEqual(options[self.tiles.id]["factor"], 1.0)
        self.project.tectora_apply_selection(
            [{"record_id": self.section.id, "side": 0, "quantity": 80.0}], "surface",
            [self.supports.id, self.tiles.id, self.waste.id], list(options),
            factors={self.supports.id: 8, self.waste.id: 0.12},
        )
        by_product = {line.product_id: line.quantity for line in self.section.product_line_ids}
        self.assertEqual(by_product[self.supports], 640.0)
        self.assertEqual(by_product[self.tiles], 80.0)
        self.assertAlmostEqual(by_product[self.waste], 9.6, places=2)

        drains = {o["id"]: o["group"] for o in self.project.tectora_get_drain_options()}
        self.assertEqual(drains[self.drain_new.id], "Nieuwe tapbuis")
        self.assertEqual(drains[self.drain_guard.id], "Bolrooster / bladvanger")
        self.project.tectora_apply_selection(
            [{"record_id": self.drain.id, "side": 0, "quantity": 1}], "drainage",
            [self.drain_new.id, self.drain_guard.id], list(drains), link_field="object_id",
        )
        self.assertEqual(self.drain.product_line_ids.mapped("quantity"), [1.0, 1.0])

    def test_segments(self):
        project = self.project
        self.assertEqual(project._tectora_segment_kind("08. Terrasvloer"), "other")
        self.assertEqual(project._tectora_segment_kind("OPBOUWWERKEN THV DAKTERRAS"), "buildup")
        self.assertEqual(project._tectora_segment_kind("AFBOUWWERKEN THV HET PLAT DAKTERRAS"), "demolition")
        self.assertEqual(project._tectora_segment_title("other", chapter=self.terrace), "AANLEG TERRASVLOER")
        self.assertEqual(project._tectora_segment_title("other", chapter=self.worst), "WORST CASE SCENARIO")
        self.assertIn("worst case", project._tectora_conditional_chapter().name.lower())

    def test_conditional_item(self):
        """A worst case item is on the quotation with a quantity of 0, under
        the worst case chapter, and does not count."""
        self._line(self.tiles)
        self._line(self.vapour, is_conditional=True)
        measured = self.project._tectora_measured_totals()
        self.assertEqual([product for _roof, product in measured], [self.tiles])
        self.assertEqual(list(measured.values()), [80.0])
        conditional = self.project._tectora_conditional_totals()
        self.assertEqual(list(conditional.values()), [80.0])
        self.assertNotIn(self.vapour, self.project._tectora_measured_products())
        self.project.action_create_sale_order()
        order = self.project.sale_order_id
        line = order.order_line.filtered(lambda l: l.product_id == self.vapour)
        self.assertEqual(len(line), 1)
        self.assertTrue(line.tectora_conditional)
        self.assertEqual(line.product_uom_qty, 0.0)
        self.assertIn("80", line.name)
        header = order.order_line.filtered(
            lambda l: l.display_type == "line_section" and l.sequence < line.sequence
        ).sorted("sequence")[-1:]
        self.assertEqual(header.name, "WORST CASE SCENARIO")
        tiles = order.order_line.filtered(lambda l: l.product_id == self.tiles)
        self.assertEqual(tiles.product_uom_qty, 80.0)
