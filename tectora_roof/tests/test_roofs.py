# -*- coding: utf-8 -*-
"""A roof project with several roofs: one plan each, and a subsection per
roof under the afbouw- and opbouwwerken of the quotation."""
import json

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRoofs(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        m2 = env.ref("uom.product_uom_square_meter")
        unit = env.ref("uom.product_uom_unit")
        root = env["product.category"].create({"name": "Werken"})
        cls.categ_demolition = env["product.category"].create(
            {"name": "03. Afbraakwerken plat dak", "parent_id": root.id}
        )
        cls.categ_buildup = env["product.category"].create(
            {"name": "04. Opbouwwerken plat dak", "parent_id": root.id}
        )
        Product = env["product.product"]
        cls.strip = Product.create({
            "name": "Bestaande bedekking verwijderen", "type": "service",
            "uom_id": m2.id, "categ_id": cls.categ_demolition.id, "list_price": 8,
        })
        cls.epdm = Product.create({
            "name": "EPDM 1,5 mm", "type": "consu", "uom_id": m2.id,
            "categ_id": cls.categ_buildup.id, "list_price": 30,
        })
        cls.fee = Product.create({
            "name": "Vaste kosten", "type": "service", "uom_id": unit.id, "list_price": 250,
        })
        cls.template = env["sale.order.template"].create({
            "name": "Renovatie plat dak test",
            "sale_order_template_line_ids": [
                Command.create({"display_type": "line_section", "name": "ALGEMENE WERKEN"}),
                Command.create({"product_id": cls.fee.id, "product_uom_qty": 1}),
                Command.create({"display_type": "line_section", "name": "AFBOUWWERKEN THV PLAT DAK"}),
                Command.create({"product_id": cls.strip.id, "product_uom_qty": 100}),
                Command.create({"display_type": "line_section", "name": "OPBOUWWERKEN THV PLAT DAK"}),
                Command.create({"product_id": cls.epdm.id, "product_uom_qty": 100}),
                Command.create({"display_type": "line_section", "name": "COMMERCIËLE TEGEMOETKOMING"}),
            ],
        })
        cls.partner = env["res.partner"].create({"name": "Klant Daken"})

    def make_order(self, template=None):
        form = Form(self.env["sale.order"])
        form.partner_id = self.partner
        form.sale_order_template_id = template or self.template
        return form.save()

    def add_roofs(self, order, *descriptions):
        action = order.action_tectora_add_roofs()
        form = Form(self.env[action["res_model"]].with_context(**action["context"]))
        form.roof_count = len(descriptions)
        for index, description in enumerate(descriptions):
            with form.line_ids.edit(index) as line:
                line.description = description
        form.save().action_apply()

    def layout(self, order):
        """The quotation as (display_type or product name, roof name)."""
        return [
            (line.display_type or line.product_id.name, line.tectora_roof_id.name or "")
            for line in order.order_line.sorted("sequence")
            if not line.roof_measurement_line
        ]

    def test_template_type(self):
        self.assertEqual(self.template.tectora_project_type, "renovatie")
        new_build = self.env["sale.order.template"].create({"name": "Nieuwbouw carport"})
        self.assertEqual(new_build.tectora_project_type, "nieuwbouw")

    def test_template_first(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        with self.assertRaises(UserError):
            order.action_tectora_add_roofs()

    def test_subsection_per_roof(self):
        order = self.make_order()
        self.add_roofs(order, "Garage", "Achterbouw")
        project = order.roof_project_id
        roofs = project.roof_ids
        self.assertEqual(roofs.mapped("name"), ["Dak 1", "Dak 2"])
        self.assertEqual(roofs.mapped("description"), ["Garage", "Achterbouw"])
        self.assertEqual(project.active_roof_id, roofs[0])
        self.assertEqual(self.layout(order), [
            ("line_section", ""), ("Vaste kosten", ""),
            ("line_section", ""),
            ("line_subsection", "Dak 1"), ("Bestaande bedekking verwijderen", "Dak 1"),
            ("line_subsection", "Dak 2"), ("Bestaande bedekking verwijderen", "Dak 2"),
            ("line_section", ""),
            ("line_subsection", "Dak 1"), ("EPDM 1,5 mm", "Dak 1"),
            ("line_subsection", "Dak 2"), ("EPDM 1,5 mm", "Dak 2"),
            ("line_section", ""),
        ])
        subsection = order.order_line.filtered(
            lambda l: l.display_type == "line_subsection" and l.tectora_roof_id == roofs[1]
        )[:1]
        self.assertEqual(subsection.name, "Dak 2 – Achterbouw")
        # Every roof has its own lines on the roof project.
        epdm_lines = project.direct_line_ids.filtered(lambda l: l.product_id == self.epdm)
        self.assertEqual(epdm_lines.roof_id, roofs)
        # Renaming a roof renames its subsections.
        roofs[1].description = "Bijgebouw"
        self.assertEqual(subsection.name, "Dak 2 – Bijgebouw")

    def test_quantities_follow_the_roofs_plan(self):
        order = self.make_order()
        self.add_roofs(order, "Garage", "Achterbouw")
        project = order.roof_project_id
        first, second = project.roof_ids
        self.env["tectora.roof.section"].create({
            "project_id": project.id, "roof_id": second.id, "name": "Achterbouw",
            "area": 30.0, "perimeter": 22.0,
        })
        project._tectora_mirror_to_order()  # what a drawing sync does
        epdm = order.order_line.filtered(lambda l: l.product_id == self.epdm)
        by_roof = {line.tectora_roof_id: line.product_uom_qty for line in epdm}
        self.assertEqual(by_roof[second], 30.0, "the second roof's plan is drawn")
        self.assertEqual(by_roof[first], 100.0, "not drawn yet: the template's quantity")

    def test_new_build_has_no_demolition(self):
        template = self.template.copy({"name": "Nieuwbouw plat dak test"})
        template.sale_order_template_line_ids.filtered(
            lambda l: l.product_id == self.strip or "AFBOUW" in (l.name or "")
        ).unlink()
        order = self.make_order(template)
        self.add_roofs(order, "Woning")
        subsections = order.order_line.filtered(lambda l: l.display_type == "line_subsection")
        self.assertEqual(len(subsections), 1)

    def test_one_plan_per_roof(self):
        order = self.make_order()
        project = order.roof_project_id
        first_plan = json.dumps({"shapes": [{"id": "a", "points": [[0, 0], [100, 0], [100, 100], [0, 100]]}]})
        project.canvas_data = first_plan
        project.action_sync_from_canvas()
        self.add_roofs(order, "Garage", "Achterbouw")
        first, second = project.roof_ids
        # The first roof took over what was drawn.
        self.assertEqual(project.section_ids.roof_id, first)
        self.assertEqual(first.canvas_data, first_plan)
        second.action_open_plan()
        self.assertEqual(project.active_roof_id, second)
        self.assertEqual(json.loads(project.canvas_data)["shapes"], [])
        second_plan = json.dumps({"shapes": [{"id": "b", "points": [[0, 0], [50, 0], [50, 50]]}]})
        project.canvas_data = second_plan
        project.action_sync_from_canvas()
        self.assertEqual(second.canvas_data, second_plan, "the drawing is kept on its roof")
        self.assertEqual(len(project.section_ids), 2, "the first roof keeps its section")
        self.assertEqual(second.section_ids.canvas_ref, "b")
        first.action_open_plan()
        self.assertEqual(project.canvas_data, first_plan)
        self.assertEqual(first.section_ids.canvas_ref, "a")
