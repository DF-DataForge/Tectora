# -*- coding: utf-8 -*-
import json

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlan(TransactionCase):
    """From the plan document to rooms and surfaces, to the quotation and to
    the material list."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env["product.product"]
        cls.customer = cls.env["res.partner"].create({"name": "Familie Peeters"})
        cls.work_walls = Product.create({
            "name": "Muren schilderen", "type": "service", "list_price": 12.0,
        })
        cls.work_ceiling = Product.create({
            "name": "Plafond schilderen", "type": "service", "list_price": 14.0,
        })
        cls.work_skirting = Product.create({
            "name": "Plinten lakken", "type": "service", "list_price": 6.0,
        })
        cls.primer = Product.create({"name": "Primer", "type": "consu", "standard_price": 8.0})
        cls.wall_paint = Product.create({"name": "Muurverf mat", "type": "consu", "standard_price": 10.0})
        cls.wall_paint.product_tmpl_id.schldr_pack_size_ids = [
            (0, 0, {"volume": 1.0}), (0, 0, {"volume": 2.5}), (0, 0, {"volume": 10.0}),
        ]
        cls.white = cls.env["schldr.colour"].create({"name": "Wit", "code": "RAL 9010", "hex": "#F1ECE1"})
        cls.green = cls.env["schldr.colour"].create({"name": "Salie", "code": "S 3010-G30Y", "hex": "#9AA58B"})
        System = cls.env["schldr.paint.system"]
        cls.walls = System.create({
            "name": "Muren: primer + 2 lagen",
            "product_id": cls.work_walls.id,
            "on_walls": True,
            "prep_hours": 0.05,
            "layer_ids": [
                (0, 0, {"role": "primer", "product_id": cls.primer.id, "coats": 1,
                        "spreading_rate": 8.0, "waste_pct": 0.0, "hours_per_coat": 0.04,
                        "tinted": False}),
                (0, 0, {"role": "finish", "product_id": cls.wall_paint.id, "coats": 2,
                        "spreading_rate": 10.0, "waste_pct": 10.0, "hours_per_coat": 0.05}),
            ],
        })
        cls.ceilings = System.create({
            "name": "Plafond: 2 lagen",
            "product_id": cls.work_ceiling.id,
            "on_walls": False, "on_ceilings": True,
            "layer_ids": [
                (0, 0, {"role": "finish", "product_id": cls.wall_paint.id, "coats": 2,
                        "spreading_rate": 10.0, "waste_pct": 10.0, "hours_per_coat": 0.06}),
            ],
        })
        cls.skirting = System.create({
            "name": "Plinten lakken",
            "product_id": cls.work_skirting.id,
            "sale_measure": "m",
            "on_walls": False, "on_woodwork": True,
        })
        cls.cover = Product.create({"name": "Vloeren afdekken", "type": "service", "list_price": 2.0})

    def _document(self, living_height=2600, accent=True):
        living = {
            "id": "R1", "name": "Woonkamer", "height": living_height,
            "points": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]],
            "walls": [{"id": "W1"}, {"id": "W2"}, {"id": "W3"}, {"id": "W4"}],
            "openings": [{"id": "O1", "wall": "W1", "kind": "door", "offset": 500,
                          "width": 900, "height": 2100}],
            "assign": {},
        }
        if accent:
            living["assign"]["R1:wall:W3"] = [{"system": self.walls.id, "colour": self.green.id}]
        bedroom = {
            "id": "R2", "name": "Slaapkamer", "height": 2500,
            "points": [[6000, 0], [9000, 0], [9000, 3000], [6000, 3000]],
            "walls": [{"id": "W5"}, {"id": "W6"}, {"id": "W7"}, {"id": "W8"}],
            "assign": {"R2:skirting": []},
        }
        return json.dumps({
            "schema": 1,
            "defaults": {"height": 2600, "assign": {
                "walls": [{"system": self.walls.id, "colour": self.white.id}],
                "ceilings": [{"system": self.ceilings.id, "colour": self.white.id}],
                "woodwork": [{"system": self.skirting.id, "colour": self.white.id}],
            }},
            "levels": [{"id": "L1", "name": "Gelijkvloers", "rooms": [living, bedroom]}],
        })

    def _project(self, **values):
        project = self.env["schldr.project"].create(dict({
            "name": "Peeters", "partner_id": self.customer.id,
            "canvas_data": self._document(),
        }, **values))
        project.action_sync_from_canvas()
        return project

    def test_sync_builds_rooms_surfaces_and_assignments(self):
        project = self._project()
        self.assertEqual(project.state, "measured")
        self.assertEqual(project.room_ids.mapped("name"), ["Woonkamer", "Slaapkamer"])
        living, bedroom = project.room_ids
        self.assertAlmostEqual(living.floor_area, 20.0)
        self.assertAlmostEqual(living.wall_area, 46.8 - 1.89, places=2)
        self.assertAlmostEqual(bedroom.wall_area, 30.0)
        self.assertAlmostEqual(project.total_ceiling_area, 29.0)
        accent = project.surface_ids.filtered(lambda s: s.canvas_ref == "R1:wall:W3")
        self.assertEqual(accent.assignment_ids.colour_id, self.green)
        other = project.surface_ids.filtered(lambda s: s.canvas_ref == "R1:wall:W1")
        self.assertEqual(other.assignment_ids.colour_id, self.white)
        self.assertAlmostEqual(other.assignment_ids.quantity, 13.0 - 1.89, places=2)
        # the bedroom said: no paint on its skirting; the living room follows the default
        self.assertFalse(project.surface_ids.filtered(lambda s: s.canvas_ref == "R2:skirting").assignment_ids)
        skirting = project.surface_ids.filtered(lambda s: s.canvas_ref == "R1:skirting")
        self.assertAlmostEqual(skirting.assignment_ids.quantity, 18.0 - 0.9)

    def test_sync_twice_keeps_the_records(self):
        project = self._project()
        before = (project.room_ids.ids, project.surface_ids.ids, project.assignment_ids.ids)
        project.action_sync_from_canvas()
        self.assertEqual(before, (project.room_ids.ids, project.surface_ids.ids, project.assignment_ids.ids))

    def test_removed_room_and_unknown_system(self):
        project = self._project()
        doc = json.loads(project.canvas_data)
        doc["levels"][0]["rooms"].pop()
        doc["levels"][0]["rooms"][0]["assign"]["R1:wall:W2"] = [{"system": 999999, "colour": False}]
        project.canvas_data = json.dumps(doc)
        project.action_sync_from_canvas()
        self.assertEqual(project.room_ids.mapped("name"), ["Woonkamer"])
        self.assertFalse(project.surface_ids.filtered(lambda s: s.canvas_ref == "R1:wall:W2").assignment_ids)

    def test_quotation_per_room_keeps_prices_when_the_plan_changes(self):
        project = self._project()
        project.line_ids = [(0, 0, {"product_id": self.cover.id, "basis": "floor", "factor": 1.0})]
        project.quote_notes = "Kleuren te bevestigen voor de start."
        project.action_create_sale_order()
        order = project.sale_order_id
        self.assertEqual(project.state, "quoted")
        names = order.order_line.mapped(lambda l: l.display_type and l.name or l.product_id.name)
        self.assertEqual(names, [
            "ALGEMENE WERKEN", "Vloeren afdekken",
            "WOONKAMER", "Muren schilderen", "Muren schilderen", "Plafond schilderen", "Plinten lakken",
            "SLAAPKAMER", "Muren schilderen", "Plafond schilderen",
            "ALGEMENE NOTA'S", "Kleuren te bevestigen voor de start.",
        ])
        cover = order.order_line.filtered(lambda l: l.product_id == self.cover)
        self.assertAlmostEqual(cover.product_uom_qty, 29.0)
        white_walls = order.order_line.filtered(
            lambda l: l.schldr_line_key == "room:R1|walls|%s|%s" % (self.walls.id, self.white.id)
        )
        self.assertAlmostEqual(white_walls.product_uom_qty, 46.8 - 1.89 - 13.0, places=2)
        self.assertIn("RAL 9010", white_walls.name)
        self.assertEqual(white_walls.schldr_colour_id, self.white)
        self.assertAlmostEqual(white_walls.price_unit, 12.0)

        # a price agreed with the customer and a line of the user's own
        white_walls.price_unit = 9.5
        extra = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.cover.id, "product_uom_qty": 3,
            "sequence": white_walls.sequence,
        })
        # the living room turns out higher, and loses its accent wall
        project.canvas_data = self._document(living_height=3000, accent=False)
        project.action_sync_from_canvas()
        self.assertAlmostEqual(white_walls.product_uom_qty, 46.8 - 1.89 - 13.0, places=2,
                               msg="the quotation does not follow the plan unasked")
        project.action_create_sale_order()
        self.assertTrue(white_walls.exists())
        self.assertAlmostEqual(white_walls.product_uom_qty, 18 * 3.0 - 1.89, places=2)
        self.assertAlmostEqual(white_walls.price_unit, 9.5)
        self.assertTrue(extra.exists())
        self.assertFalse(order.order_line.filtered(
            lambda l: l.schldr_line_key and str(self.green.id) == l.schldr_line_key.split("|")[-1]
        ), "the accent wall is gone from the quotation")
        ordered = order.order_line.sorted(lambda l: (l.sequence, l.id))
        self.assertEqual(ordered[ordered.ids.index(white_walls.id) + 1], extra,
                         "the user's line stays after the line it followed")

    def test_quotation_follows_the_measurement_when_asked(self):
        project = self._project()
        project.action_create_sale_order()
        order = project.sale_order_id
        order.schldr_follow_measurement = True
        ceiling = order.order_line.filtered(lambda l: (l.schldr_line_key or "").startswith("room:R2|ceilings"))
        self.assertAlmostEqual(ceiling.product_uom_qty, 9.0)
        doc = json.loads(project.canvas_data)
        doc["levels"][0]["rooms"][1]["points"] = [[6000, 0], [10000, 0], [10000, 3000], [6000, 3000]]
        project.canvas_data = json.dumps(doc)
        project.action_sync_from_canvas()
        self.assertAlmostEqual(ceiling.product_uom_qty, 12.0)
        order.action_schldr_toggle_lock()
        doc["levels"][0]["rooms"][1]["points"] = [[6000, 0], [11000, 0], [11000, 3000], [6000, 3000]]
        project.canvas_data = json.dumps(doc)
        project.action_sync_from_canvas()
        self.assertAlmostEqual(ceiling.product_uom_qty, 12.0, msg="a locked quotation is left alone")

    def test_quotation_per_system(self):
        project = self._project(quote_grouping="system")
        project.action_create_sale_order()
        order = project.sale_order_id
        sections = order.order_line.filtered(lambda l: l.display_type == "line_section").mapped("name")
        self.assertEqual(sections, ["SCHILDERWERKEN"])
        white_walls = order.order_line.filtered(
            lambda l: l.schldr_line_key == "works|walls|%s|%s" % (self.walls.id, self.white.id)
        )
        self.assertAlmostEqual(white_walls.product_uom_qty, 46.8 - 1.89 - 13.0 + 30.0, places=2)

    def test_confirming_builds_the_material_list_per_colour(self):
        project = self._project()
        project.action_create_sale_order()
        order = project.sale_order_id
        order.action_confirm()
        self.assertEqual(project.state, "confirmed")
        materials = project.material_line_ids
        walls_white = 46.8 - 1.89 - 13.0 + 30.0
        primer = materials.filtered(lambda m: m.product_id == self.primer)
        self.assertEqual(len(primer), 1)
        self.assertFalse(primer.colour_id, "the primer is the same for every colour")
        self.assertAlmostEqual(primer.quantity_needed, (walls_white + 13.0) / 8.0, places=2)
        green = materials.filtered(lambda m: m.product_id == self.wall_paint and m.colour_id == self.green)
        self.assertAlmostEqual(green.quantity_needed, 13.0 * 2 * 1.1 / 10.0, places=2)
        self.assertEqual(green.quantity, 3.5)
        self.assertEqual(green.pack_summary, "1 x 2,5 Units + 1 x 1 Units")
        white = materials.filtered(lambda m: m.product_id == self.wall_paint and m.colour_id == self.white)
        need = (walls_white + 29.0) * 2 * 1.1 / 10.0
        self.assertAlmostEqual(white.quantity_needed, need, places=2)
        self.assertGreaterEqual(white.quantity, need)
        # the works are services: no material line for them
        self.assertFalse(materials.filtered(lambda m: m.product_id == self.work_walls))

    def test_hours_of_the_system_size_the_tasks(self):
        self.assertAlmostEqual(self.work_walls.schldr_hours_preparation_per_uom, 0.05)
        self.assertAlmostEqual(self.work_walls.schldr_hours_execution_per_uom, 0.04 + 2 * 0.05)
        project = self._project()
        project.action_create_sale_order()
        order = project.sale_order_id
        walls = 46.8 - 1.89 + 30.0
        self.assertAlmostEqual(order.schldr_preparation_hours, walls * 0.05, places=1)
        self.assertAlmostEqual(order.schldr_execution_hours, walls * 0.14 + 29.0 * 0.12, places=1)
        order.action_confirm()
        tasks = project.project_id.task_ids.filtered("schldr_work_kind")
        self.assertEqual(set(tasks.mapped("schldr_work_kind")), {"voorbereiding", "uitvoering"})

    def test_colour_schedule_and_plan_image(self):
        project = self._project()
        schedule = project._schldr_colour_schedule()
        self.assertEqual([entry["room"] for entry in schedule], ["Woonkamer", "Slaapkamer"])
        self.assertEqual(
            [(row["group"], row["colour"]) for row in schedule[0]["rows"]],
            [("Muren", "RAL 9010 Wit"), ("Muren", "S 3010-G30Y Salie"),
             ("Plafonds", "RAL 9010 Wit"), ("Houtwerk", "RAL 9010 Wit")],
        )
        png = project._get_drawing_png()
        self.assertTrue(png and png[:4] == b"\x89PNG")
        plans = project._schldr_plans()
        self.assertEqual(len(plans), 1)
        self.assertTrue(plans[0]["image"].startswith("data:image/png"))

    def test_plan_options(self):
        options = self.env["schldr.project"].schldr_get_plan_options()
        system = next(s for s in options["systems"] if s["id"] == self.walls.id)
        self.assertEqual(system["groups"], ["walls"])
        self.assertEqual(system["measure"], "m2")
        self.assertEqual(len(system["layers"]), 2)
        self.assertTrue(any(c["hex"] == "#9AA58B" for c in options["colours"]))
        self.assertTrue(any(e["kind"] == "door" for e in options["element_types"]))
