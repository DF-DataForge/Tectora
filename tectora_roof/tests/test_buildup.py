# -*- coding: utf-8 -*-
"""The standard build-up of a roof surface (dampscherm, isolatie,
dakbedekking) and the EPDM sheets calculated from the drawing."""
import json

from odoo.tests import TransactionCase, tagged

from ..models.roof_buildup import epdm_sheet_size


@tagged("post_install", "-at_install")
class TestBuildup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        Category = env["product.category"]
        root = Category.create({"name": "Dakwerken test"})
        buildup = Category.create({"name": "04. Opbouwwerken plat dak", "parent_id": root.id})
        surface = env["tectora.roof.usage"].search([("code", "=", "surface")], limit=1) or \
            env["tectora.roof.usage"].create({"name": "Oppervlaktes", "code": "surface"})
        cls.insulation_categ = Category.create({
            "name": "Isolatie", "parent_id": buildup.id,
            "tectora_usage_ids": [(6, 0, surface.ids)],
        })
        cls.pir_categ = Category.create({"name": "PIR", "parent_id": cls.insulation_categ.id})
        vapour_categ = Category.create({"name": "Dampscherm", "parent_id": buildup.id})
        membrane_categ = Category.create({"name": "Dakbedekking", "parent_id": buildup.id})
        Product = env["product.product"]

        def product(name, categ, price):
            return Product.create({
                "name": name, "type": "service", "uom_id": m2.id,
                "categ_id": categ.id, "list_price": price, "sale_ok": True,
            })

        cls.vapour = product("Leveren en plaatsen van het dampscherm klasse E3 type: Sopraglass V3",
                             vapour_categ, 16.37)
        cls.pir_10 = product("Leveren en plaatsen isolatie type: Unilin Utherm Roof PIR dikte: 10cm "
                             "(600x1200) verkleefd", cls.pir_categ, 49.58)
        cls.pir_12 = product("Leveren en plaatsen isolatie type: Unilin Utherm Roof PIR dikte: 12cm "
                             "(600x1200) mechanisch", cls.pir_categ, 52.55)
        cls.epdm = product("Leveren en plaatsen van de dakbedekking type: Elevate Rubbergard EPDM "
                           "1,5mm dik verkleefd", membrane_categ, 49.99)

        # One roof surface of 10 x 6 m (0.02 m/px) with a seam across at
        # x = 5 m: one section, two EPDM sheets. Roof edges 0.30 m wide with
        # a 0.20 m upstand on every side.
        all_sides = {str(i): 0.3 for i in range(4)}
        drawing = {"shapes": [
            {"id": "a", "kind": "section", "name": "Sectie 1",
             "points": [[0, 0], [500, 0], [500, 300], [0, 300]],
             "edgeWidths": all_sides, "edgeUpstands": {str(i): 0.2 for i in range(4)}},
            {"id": "n", "kind": "seam", "name": "Naad 1",
             "points": [[250, 0], [250, 300]]},
        ]}
        cls.project = env["tectora.roof.project"].create({
            "name": "Dakopbouw", "partner_id": env["res.partner"].create({"name": "Klant"}).id,
            "scale_m_per_px": 0.02, "canvas_data": json.dumps(drawing),
        })
        cls.project.action_sync_from_canvas()
        cls.sections = cls.project.section_ids.sorted("name")

    def test_sheet_size_geometry(self):
        # 9.40 x 5.40 m surface, 0.60 m beyond every side.
        self.assertEqual(
            tuple(round(v, 2) for v in epdm_sheet_size(
                [(0, 0), (9.4, 0), (9.4, 5.4), (0, 5.4)], [0.6] * 4)),
            (10.6, 6.6),
        )

    def test_category_inherits_usages(self):
        ids = self.env["product.category"].tectora_category_ids_for_usages(["surface"])
        self.assertIn(self.pir_categ.id, ids, "a sub-category is offered where its parent is")
        self.assertNotIn(self.pir_categ.id,
                         self.env["product.category"].tectora_category_ids_for_usages(["edge"]))

    def test_options(self):
        options = self.project.tectora_get_buildup_options()["options"]
        insulation = {o["id"]: o for o in options["insulation"]}
        self.assertEqual(insulation[self.pir_10.id]["type"], "Unilin Utherm Roof PIR")
        self.assertEqual(insulation[self.pir_10.id]["thickness"], 100.0)
        self.assertEqual(insulation[self.pir_12.id]["fixing"], "mechanisch")
        membrane = next(o for o in options["membrane"] if o["id"] == self.epdm.id)
        self.assertEqual((membrane["type"], membrane["thickness"]), ("Elevate Rubbergard EPDM", 1.5))
        self.assertIn(self.vapour.id, [o["id"] for o in options["vapour"]])

    def test_apply_and_sheets(self):
        self.assertEqual(len(self.sections), 1, "a seam no longer splits the surface")
        result = self.project.tectora_apply_buildup(
            self.sections.ids, vapour_id=self.vapour.id, insulation_id=self.pir_10.id,
            membrane_id=self.epdm.id, sheets=True, margin=0.1,
        )
        for section in self.sections:
            surface = section.product_line_ids.filtered(lambda l: l.coverage == "surface")
            self.assertEqual(surface.product_id, self.vapour | self.pir_10 | self.epdm)
        self.assertEqual(result["lines"], 3)
        # The seam divides the surface into two sheets. Each: 4.70 x 5.40 m
        # inside the edges, +0.60 m (0.30 edge, 0.20 upstand, 0.10 margin) on
        # the outer sides, +0.10 m (overlap) on the seam.
        sheets = self.project.epdm_sheet_ids.filtered("section_id").sorted("name")
        self.assertEqual(len(sheets), 2)
        self.assertEqual(sheets.section_id, self.sections)
        for sheet in sheets:
            self.assertEqual((sheet.length, sheet.width), (6.6, 5.4))
        self.assertEqual(self.project.epdm_thickness, 1.5)

        # Another insulation replaces the first; the sheets are recalculated,
        # not added.
        self.project.tectora_apply_buildup(
            self.sections[:1].ids, insulation_id=self.pir_12.id, sheets=True, margin=0.1,
        )
        products = self.sections[0].product_line_ids.product_id
        self.assertIn(self.pir_12, products)
        self.assertNotIn(self.pir_10, products)
        self.assertIn(self.epdm, products, "a layer left out is not touched")
        self.assertEqual(len(self.project.epdm_sheet_ids.filtered("section_id")), 2)
        self.assertEqual(self.project.buildup_insulation_id, self.pir_12)
