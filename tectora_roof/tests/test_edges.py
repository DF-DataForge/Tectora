# -*- coding: utf-8 -*-
"""The finish of a roof surface's sides: a roof edge with its corners, or a
connection, each from its own products."""
import json

from odoo.tests import TransactionCase, tagged

from ..models.roof_edges import corner_kind, edge_info


@tagged("post_install", "-at_install")
class TestEdges(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        env = cls.env
        meter = env.ref("uom.product_uom_meter")
        unit = env.ref("uom.product_uom_unit")
        Category = env["product.category"]
        edges = Category.create({"name": "02. Dakranden"})
        corners = Category.create({"name": "Hoeken & eindstukken", "parent_id": edges.id})
        connections = Category.create({"name": "Aansluitingen"})
        Product = env["product.product"]

        def product(name, categ, uom, price):
            return Product.create({
                "name": name, "type": "service", "uom_id": uom.id,
                "categ_id": categ.id, "list_price": price, "sale_ok": True,
            })

        suffix = "voor de enkelvoudige dakrandprofielen hoogte: 60mm in RAL naar keuze"
        cls.profile = product("Leveren en plaatsen van de enkelvoudige dakrandprofielen "
                              "hoogte: 60mm in RAL naar keuze", edges, meter, 33.21)
        cls.other_height = product("Leveren en plaatsen van de enkelvoudige dakrandprofielen "
                                   "hoogte: 80mm in RAL naar keuze", edges, meter, 35.03)
        cls.inner = product("Leveren en plaatsen binnenhoek " + suffix, corners, unit, 20)
        cls.outer = product("Leveren en plaatsen buitenhoek " + suffix, corners, unit, 22)
        cls.connection = product("Aansluiting van de EPDM op het dak van de buren met resitrix",
                                 connections, meter, 24.14)
        drawing = {"shapes": [{"id": "s", "kind": "section", "name": "Sectie 1",
                               "points": [[0, 0], [200, 0], [200, 200], [0, 200]]}]}
        cls.project = env["tectora.roof.project"].create({
            "name": "Randen", "partner_id": env["res.partner"].create({"name": "Klant"}).id,
            "scale_m_per_px": 0.02, "canvas_data": json.dumps(drawing),
        })
        cls.project.action_sync_from_canvas()
        cls.section = cls.project.section_ids

    def test_edge_info(self):
        info = edge_info(self.outer.name)
        self.assertEqual((info["type"], info["height"], info["finish"], info["corner"]),
                         ("Enkelvoudige dakrand", 60, "RAL naar keuze", "outer"))
        self.assertEqual(corner_kind([(0, 0), (10, 0), (10, 10), (5, 10), (5, 5), (0, 5)], 4), "inner")

    def test_options(self):
        options = self.project.tectora_get_edge_options()
        self.assertEqual({o["id"] for o in options["edges"]}, {self.profile.id, self.other_height.id})
        self.assertEqual([o["id"] for o in options["connections"]], [self.connection.id])
        self.assertEqual(options["connections"][0]["group"], "Dak van de buren")

    def test_edge_with_corners_then_connection(self):
        items = [{"section_id": self.section.id, "side": 1, "quantity": 4.0},
                 {"section_id": self.section.id, "side": 2, "quantity": 4.0}]
        preview = self.project.tectora_apply_edges(items, "edge", self.profile.id, dry_run=True)
        self.assertEqual(preview["corners"], {"inner": 0, "outer": 1})
        self.assertFalse(self.section.product_line_ids)

        self.project.tectora_apply_edges(items, "edge", self.profile.id)
        lines = self.section.product_line_ids
        sides = lines.filtered(lambda l: l.coverage == "edges")
        self.assertEqual(sorted(sides.mapped("edge_index")), [1, 2])
        self.assertEqual(sides.product_id, self.profile)
        corner = lines.filtered(lambda l: l.coverage == "corners")
        # Corner 2 joins sides 1 and 2.
        self.assertEqual((corner.edge_index, corner.product_id), (2, self.outer))

        # Side 2 against the neighbours' roof: a connection replaces the
        # roof edge, and the corner piece goes.
        self.project.tectora_apply_edges(
            [{"section_id": self.section.id, "side": 2, "quantity": 4.0}],
            "connection", self.connection.id,
        )
        lines = self.section.product_line_ids
        side_2 = lines.filtered(lambda l: l.coverage == "edges" and l.edge_index == 2)
        self.assertEqual(side_2.product_id, self.connection)
        self.assertFalse(lines.filtered(lambda l: l.coverage == "corners"))
