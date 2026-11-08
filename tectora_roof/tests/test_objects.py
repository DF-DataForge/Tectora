# -*- coding: utf-8 -*-
"""The calculators of the roof objects: the chimney's cladding and the
Skylux dome, priced from the Skylux price table."""
import json

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestObjects(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        env["product.template"]._tectora_ensure_skylux_catalog()
        m2 = env.ref("uom.product_uom_square_meter")
        cls.cladding = env["product.product"].create({
            "name": "Volledig inpakken van de schoorsteen incl. bovenzijde met isolatie 4cm & EPDM",
            "type": "service", "uom_id": m2.id, "list_price": 100.8, "sale_ok": True,
        })
        # A 1 x 1 m chimney and a 1 x 1 m dome at 0.02 m/px.
        drawing = {"shapes": [
            {"id": "s", "kind": "section", "name": "Sectie 1",
             "points": [[0, 0], [500, 0], [500, 300], [0, 300]]},
            {"id": "c", "kind": "chimney", "name": "Schoorsteen",
             "points": [[100, 100], [150, 100], [150, 150], [100, 150]]},
            {"id": "k", "kind": "skylight", "name": "Koepel",
             "points": [[300, 100], [350, 100], [350, 150], [300, 150]]},
        ]}
        cls.project = env["tectora.roof.project"].create({
            "name": "Objecten", "partner_id": env["res.partner"].create({"name": "Klant"}).id,
            "scale_m_per_px": 0.02, "canvas_data": json.dumps(drawing),
        })
        cls.project.action_sync_from_canvas()
        objects = cls.project.roof_object_ids
        cls.chimney = objects.filtered(lambda o: o.object_type == "chimney")
        cls.dome = objects.filtered(lambda o: o.object_type == "skylight")

    def test_chimney(self):
        self.project.tectora_apply_chimney(self.chimney.id, self.cladding.id, height=1.5)
        line = self.chimney.product_line_ids
        self.assertEqual(line.product_id, self.cladding)
        # Sides 4 m x 1.5 m, and the top (wrapped completely) 1 m².
        self.assertAlmostEqual(line.quantity, 7.0, places=2)
        options = self.project.tectora_get_chimney_options(self.chimney.id)
        self.assertEqual(options["current"], self.cladding.id)

    def test_skylux_dome(self):
        Price = self.env["tectora.skylux.price"]
        Price.create({"line": "dome", "option": "Acrylaat driewandig helder", "size": "100 x 100 cm",
                      "price": 410.0, "cost": 250.0})
        Price.create({"line": "curb", "option": "16/20 EP · Opengaand", "size": "100 x 100 cm",
                      "price": 520.0, "cost": 300.0})
        options = self.project.tectora_get_skylight_options(self.dome.id)
        self.assertEqual(options["current"]["size"], "100 x 100 cm", "the drawn dome's size")
        result = self.project.tectora_apply_skylight(self.dome.id, {
            "mode": "set", "size": "100 x 100 cm",
            "dome": "Acrylaat driewandig helder", "curb": "16/20 EP · Opengaand", "extras": [],
        })
        self.assertEqual(result, {"lines": 2, "missing": []})
        prices = sorted(self.dome.product_line_ids.mapped("product_id.lst_price"))
        self.assertEqual(prices, [410.0, 520.0])
        # The variants are made only now, and only these.
        dome_template = self.env["product.template"].search([("tectora_skylux_line", "=", "dome")])
        self.assertEqual(len(dome_template.product_variant_ids), 1)
        # Applying again replaces, and remembers the choice.
        self.project.tectora_apply_skylight(self.dome.id, {
            "mode": "rwa", "size": "100 x 100 cm", "rwa": "Driewandig · Helder", "extras": [],
        })
        self.assertEqual(len(self.dome.product_line_ids), 1)
        current = self.project.tectora_get_skylight_options(self.dome.id)["current"]
        self.assertEqual((current["mode"], current["rwa"]), ("rwa", "Driewandig · Helder"))

    def test_kimfix(self):
        meter = self.env.ref("uom.product_uom_meter")
        kimfix = self.env["product.product"].create({
            "name": "Leveren en plaatsen van de mechanische verankering thv de opstanden 'kimfixatie'",
            "type": "service", "uom_id": meter.id, "list_price": 19.29, "sale_ok": True,
        })
        section = self.project.section_ids
        self.assertEqual(section.kimfix_object_perimeter, 8.0)
        self.project.tectora_apply_buildup(section.ids, kimfix=True)
        line = section.product_line_ids.filtered(lambda l: l.product_id == kimfix)
        # All 32 m of sides, and around the chimney and the dome (2 x 4 m).
        self.assertAlmostEqual(line.quantity, 40.0, places=2)
        self.project.tectora_apply_buildup(section.ids, kimfix=False)
        self.assertFalse(section.product_line_ids.filtered(lambda l: l.product_id == kimfix))
