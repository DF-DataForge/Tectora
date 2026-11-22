# -*- coding: utf-8 -*-
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProductDimensions(TransactionCase):
    """The dimensions of a hercalculatie product are entered in mm and kept
    (and calculated with) in m."""

    def test_entered_in_mm(self):
        with Form(self.env["product.template"]) as form:
            form.name = "Dakrandprofiel"
            form.schldr_recalc = True
            form.schldr_recalc_uom = "m"
            form.schldr_length_mm = 3000
            form.schldr_width_mm = 64
            form.schldr_height_mm = 80
        template = form.record
        self.assertAlmostEqual(template.schldr_length, 3.0)
        self.assertAlmostEqual(template.schldr_width, 0.064)
        self.assertAlmostEqual(template.schldr_height, 0.08)
        self.assertAlmostEqual(template.schldr_recalc_size, 3.0)
        self.assertEqual(template._schldr_recalculate(10.0), 4.0, "10 m of 3 m pieces")

    def test_existing_metres_shown_in_mm(self):
        template = self.env["product.template"].create({
            "name": "Isolatieplaat", "schldr_recalc": True, "schldr_recalc_uom": "m2",
            "schldr_length": 1.2, "schldr_width": 0.6,
        })
        self.assertAlmostEqual(template.schldr_length_mm, 1200.0)
        self.assertAlmostEqual(template.schldr_width_mm, 600.0)
        template.schldr_width_mm = 500
        self.assertAlmostEqual(template.schldr_recalc_size, 0.6)

    def test_switched_on_from_the_variant(self):
        """From a component (product.product) hercalculatie, unit and
        dimensions are saved together; the check sees them all."""
        template = self.env["product.template"].create({"name": "Dakrand DRBS 175/80"})
        variant = template.product_variant_id
        with Form(variant) as form:
            form.schldr_recalc = True
            form.schldr_recalc_uom = "m"
            form.schldr_length_mm = 3000
            form.schldr_width_mm = 64
            form.schldr_height_mm = 80
        self.assertEqual(template.schldr_recalc_uom, "m")
        self.assertAlmostEqual(template.schldr_recalc_size, 3.0)
        variant.write({"schldr_recalc_uom": "m2", "schldr_width": 0.5})
        self.assertAlmostEqual(template.schldr_recalc_size, 1.5)

    def test_preview_follows_mm(self):
        with Form(self.env["product.template"]) as form:
            form.name = "Plaat"
            form.schldr_recalc = True
            form.schldr_recalc_uom = "m2"
            form.schldr_length_mm = 1200
            form.schldr_width_mm = 600
            self.assertAlmostEqual(form.schldr_recalc_size, 0.72)
