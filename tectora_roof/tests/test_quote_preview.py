# -*- coding: utf-8 -*-
"""The quotation build-up beside the drawing: per chapter the products of
the drawing, with the parts of the drawing each comes from."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestQuotePreview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        meter = env.ref("uom.product_uom_meter")
        unit = env.ref("uom.product_uom_unit")
        Category = env["product.category"]
        root = Category.create({"name": "Dakwerken"})
        cls.demolition = Category.create({"name": "03. Afbraakwerken", "parent_id": root.id})
        cls.buildup = Category.create({"name": "04. Opbouwwerken plat dak", "parent_id": root.id})
        Product = env["product.product"]
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "uom_id": m2.id,
            "categ_id": cls.buildup.id, "list_price": 30,
        })
        cls.trim = Product.create({
            "name": "Daktrim", "type": "consu", "uom_id": meter.id,
            "categ_id": cls.buildup.id, "list_price": 12,
        })
        cls.strip = Product.create({
            "name": "Oude roofing verwijderen", "type": "consu", "uom_id": m2.id,
            "categ_id": cls.demolition.id, "list_price": 8,
        })
        cls.container = Product.create({
            "name": "Container", "type": "consu", "uom_id": unit.id,
            "categ_id": cls.demolition.id, "list_price": 250,
        })
        cls.project = env["tectora.roof.project"].create({
            "name": "Offerte-opbouw", "partner_id": env["res.partner"].create({"name": "Klant"}).id,
        })
        Section = env["tectora.roof.section"]
        cls.main = Section.create({
            "project_id": cls.project.id, "name": "Hoofddak", "canvas_ref": "s1",
            "area": 100.0, "perimeter": 40.0,
        })
        cls.annex = Section.create({
            "project_id": cls.project.id, "name": "Bijgebouw", "canvas_ref": "s2",
            "area": 20.0, "perimeter": 18.0,
        })
        Line = env["tectora.roof.section.product"]
        for section in (cls.main, cls.annex):
            Line.create({"section_id": section.id, "product_id": cls.epdm.id, "coverage": "surface"})
            Line.create({"section_id": section.id, "product_id": cls.strip.id, "coverage": "surface"})
        Line.create({
            "section_id": cls.main.id, "product_id": cls.trim.id,
            "coverage": "edges", "edge_index": 2, "quantity": 6.0,
        })
        Line.create({"project_direct_id": cls.project.id, "product_id": cls.container.id})
        # Superseded by the drawing, as on the quotation.
        Line.create({"project_direct_id": cls.project.id, "product_id": cls.epdm.id})

    def test_chapters_and_parts(self):
        quote = self.project.tectora_get_quote_preview()
        labels = [chapter["label"] for chapter in quote["chapters"]]
        self.assertEqual(labels, ["AFBOUWWERKEN THV HET PLAT DAK", "OPBOUWWERKEN THV HET PLAT DAK"])
        demolition, buildup = quote["chapters"]

        epdm = [line for line in buildup["lines"] if line["product_id"] == self.epdm.id]
        self.assertEqual(len(epdm), 1, "one line per product, the drawing's line only")
        self.assertEqual(epdm[0]["quantity"], 120.0)
        self.assertEqual(sorted(t["canvas_ref"] for t in epdm[0]["targets"]), ["s1", "s2"])
        self.assertEqual(epdm[0]["subtotal"], 3600.0)

        trim = next(line for line in buildup["lines"] if line["product_id"] == self.trim.id)
        self.assertEqual(trim["targets"], [{
            "canvas_ref": "s1", "kind": "section", "name": "Hoofddak",
            "coverage": "edges", "edge_index": 2,
        }])

        container = next(line for line in demolition["lines"] if line["product_id"] == self.container.id)
        self.assertTrue(container["project_line"])
        self.assertFalse(container["targets"])

        self.assertAlmostEqual(demolition["total"], 120 * 8 + 250)
        self.assertAlmostEqual(quote["total"], demolition["total"] + buildup["total"])
        self.assertTrue(quote["total_display"])
        self.assertFalse(quote["order"])

    def test_quotation_lines_in_their_segment(self):
        self.project.action_create_sale_order()
        order = self.project.sale_order_id
        extra = self.env["product.product"].create({"name": "Werfinrichting", "list_price": 500})
        self.env["sale.order.line"].create({"order_id": order.id, "product_id": extra.id})
        quote = self.project.tectora_get_quote_preview()
        self.assertEqual(quote["order"], order.name)
        # A line added on the quotation becomes a project line too, in the
        # segment of its product (no chapter: Overige).
        rows = {line["product_id"]: chapter["label"] for chapter in quote["chapters"] for line in chapter["lines"]}
        self.assertEqual(rows.get(extra.id), "OVERIGE")

    def test_builder_segments(self):
        builder = self.project.tectora_get_quote_builder()
        kinds = [segment["kind"] for segment in builder["segments"]]
        self.assertEqual(kinds, ["general", "safety", "demolition", "buildup", "notes"])
        self.project.tectora_builder_add("demolition:0", [self.container.id])
        self.assertEqual(
            len(self.project.direct_line_ids.filtered(lambda l: l.product_id == self.container)), 1,
            "a product already in the segment is not added twice",
        )
