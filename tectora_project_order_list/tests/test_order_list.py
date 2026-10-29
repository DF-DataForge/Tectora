# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrderList(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Start from an empty configuration, as the module ships it.
        cls.env["tectora.order.list.template"].search([]).action_archive()
        cls.env["tectora.task.template"].search([]).action_archive()
        cls.env["tectora.project.phase"].search([]).action_archive()
        cls.supplier = cls.env["res.partner"].create({"name": "Dakmaterialen NV"})
        cls.other_supplier = cls.env["res.partner"].create({"name": "Isolatie BV"})
        Template = cls.env["tectora.order.list.template"]
        cls.part_order = Template.create({
            "name": "Dakbedekking", "sequence": 1, "order_action": "order",
            "partner_ids": [(6, 0, (cls.supplier | cls.other_supplier).ids)],
            "supplier_note": "Levertijd 2 weken",
        })
        cls.part_stock = Template.create({
            "name": "Isolatie", "sequence": 2, "order_action": "stock_first",
        })
        phase = cls.env["tectora.project.phase"].create({"name": "Voorbereiding"})
        cls.task_template = cls.env["tectora.task.template"].create({
            "name": "Alles besteld volgens de bestellijst",
            "phase_id": phase.id, "order_list_auto": True,
        })
        cls.product = cls.env["product.product"].create({
            "name": "EPDM", "is_storable": True, "purchase_ok": True,
        })

    def _project(self):
        return self.env["project.project"].create({"name": "Werf"})

    def test_new_project_gets_order_list(self):
        project = self._project()
        lines = project.tectora_order_line_ids
        self.assertEqual(lines.mapped("name"), ["Dakbedekking", "Isolatie"])
        first = lines[0]
        self.assertEqual(first.partner_id, self.supplier, "first suggested supplier by default")
        self.assertEqual(first.supplier_note, "Levertijd 2 weken")
        self.assertEqual(first.status, "todo")
        self.assertEqual(project.tectora_order_progress, 0)

    def test_order_list_task_follows_the_list(self):
        project = self._project()
        task = self.env["project.task"].search([
            ("project_id", "=", project.id), ("tectora_template_id", "=", self.task_template.id),
        ])
        lines = project.tectora_order_line_ids
        lines[0].checked = True
        self.assertNotEqual(task.state, "1_done")
        lines[1].checked = True
        self.assertEqual(task.state, "1_done")
        self.assertTrue(task.milestone_id.is_reached)
        lines[1].action_tectora_toggle_checked()
        self.assertNotEqual(task.state, "1_done")
        data = project._tectora_task_data(task)
        self.assertEqual(data["link"]["method"], "action_tectora_open_order_board")

    def test_purchase_from_line(self):
        project = self._project()
        line = project.tectora_order_line_ids[0]
        self.env["tectora.project.order.product"].create({
            "order_line_id": line.id, "product_id": self.product.id, "quantity": 5,
        })
        action = line.action_tectora_create_purchase()
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(order.project_id, project)
        self.assertEqual(order.partner_ref, "Werf", "the site's reference for the vendor")
        roof = self.env["tectora.roof.project"].create({"name": "Werf Heule", "project_id": project.id})
        self.assertEqual(roof._tectora_vendor_reference(), f"{roof.code} · Werf Heule")
        self.assertEqual(order.tectora_order_line_id, line)
        self.assertEqual(order.order_line.product_qty, 5)
        self.assertEqual(line.status, "rfq")
        self.assertTrue(line.order_date)
        order.button_confirm()
        line.invalidate_recordset(["status"])
        self.assertEqual(line.status, "ordered")

    def test_stock_first_orders_only_the_shortage(self):
        project = self._project()
        line = project.tectora_order_line_ids[1]
        line.partner_id = self.supplier
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.env.ref("stock.stock_location_stock"), 3
        )
        self.env["tectora.project.order.product"].create({
            "order_line_id": line.id, "product_id": self.product.id, "quantity": 5,
        })
        self.assertEqual(line.product_line_ids.shortage_qty, 2)
        action = line.action_tectora_create_purchase()
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(order.order_line.product_qty, 2)

        line.product_line_ids.quantity = 2
        self.assertEqual(line.status, "rfq")
        order.button_cancel()
        line.invalidate_recordset(["status"])
        self.assertEqual(line.status, "stock")
        with self.assertRaises(UserError):
            line.action_tectora_create_purchase()

    def test_supplier_products_and_purchase_of_the_selection(self):
        project = self._project()
        line = project.tectora_order_line_ids[0]  # Dakmaterialen NV chosen
        Product = self.env["product.product"]
        membrane = Product.create({
            "name": "Dakmembraan", "purchase_ok": True,
            "seller_ids": [(0, 0, {"partner_id": self.supplier.id, "product_code": "DM-1"})],
        })
        gutter = Product.create({
            "name": "Dakgoot", "purchase_ok": True,
            "seller_ids": [(0, 0, {"partner_id": self.supplier.id})],
        })
        wool = Product.create({
            "name": "Rotswol", "purchase_ok": True,
            "seller_ids": [(0, 0, {"partner_id": self.other_supplier.id})],
        })
        self.env["tectora.project.order.product"].create({
            "order_line_id": line.id, "product_id": self.product.id, "quantity": 4,
        })
        # The project's material list: membrane twice (two order lines) and
        # the wool; not the gutter.
        roof = self.env["tectora.roof.project"].create({"name": "Werf", "project_id": project.id})
        self.env["tectora.roof.material"].create([
            {"project_id": roof.id, "product_id": membrane.id, "quantity": 30.0},
            {"project_id": roof.id, "product_id": membrane.id, "quantity": 12.5},
            {"project_id": roof.id, "product_id": wool.id, "quantity": 8.0},
        ])

        items = {item["name"]: item for item in line.tectora_get_supplier_products()}
        self.assertEqual(set(items), {"EPDM", "Dakmembraan"},
                         "the supplier's products on the material list, and those on the part")
        self.assertTrue(items["EPDM"]["selected"])
        self.assertEqual(items["EPDM"]["quantity"], 4)
        self.assertFalse(items["Dakmembraan"]["selected"])
        self.assertEqual(items["Dakmembraan"]["code"], "DM-1")
        self.assertEqual(items["Dakmembraan"]["quantity"], 42.5, "what the material list needs")
        self.assertEqual(items["Dakmembraan"]["needed"], 42.5)

        action = line.action_tectora_create_purchase(products=[
            {"product_id": membrane.id, "quantity": 12},
            {"product_id": self.product.id, "quantity": 6},
        ])
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(
            {(pl.product_id, pl.product_qty) for pl in order.order_line},
            {(membrane, 12), (self.product, 6)},
            "the request for quotation holds the selected products only",
        )
        self.assertEqual(
            {(pl.product_id, pl.quantity) for pl in line.product_line_ids},
            {(membrane, 12), (self.product, 6)},
        )
        self.assertNotIn(gutter, line.product_line_ids.product_id)
        with self.assertRaises(UserError):
            line.action_tectora_create_purchase(products=[])

        # Beyond the material list: any purchasable product, the supplier's first.
        extra = line.tectora_search_extra_products("Dak")
        self.assertEqual(
            [item["name"] for item in extra][:2], ["Dakgoot", "Dakmembraan"],
            "the supplier's products first",
        )
        self.assertTrue(all(item["from_supplier"] for item in extra[:2]))
        action = line.action_tectora_create_purchase(products=[{"product_id": gutter.id, "quantity": 3}])
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(order.order_line.product_id, gutter, "a product off the list can be ordered")

        # Without a chosen supplier: the products of the suggested ones.
        line.partner_id = False
        names = {item["name"] for item in line.tectora_get_supplier_products()}
        self.assertIn("Rotswol", names)

    def test_ordered_and_stock_products_are_set_apart(self):
        project = self._project()
        line = project.tectora_order_line_ids[0]  # Dakmaterialen NV chosen
        screws = self.env["product.product"].create({
            "name": "Schroeven", "is_storable": True, "purchase_ok": True,
        })
        stock = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(screws, stock, 10)

        # Ordered: set apart under its purchase order.
        action = line.action_tectora_create_purchase(
            products=[{"product_id": self.product.id, "quantity": 5}]
        )
        purchase = self.env["purchase.order"].browse(action["res_id"])
        data = line.tectora_get_supplier_products()
        self.assertNotIn(self.product.id, [item["id"] for item in data["items"]])
        self.assertEqual(len(data["ordered"]), 1)
        self.assertIn("Dakmaterialen NV", data["ordered"][0]["title"])
        self.assertEqual(data["ordered"][0]["reference"], purchase.name)
        self.assertEqual(data["ordered"][0]["lines"][0]["quantity"], 5)

        # From the warehouse: on an outgoing delivery that reserves the stock.
        line.action_tectora_deliver_from_stock([{"product_id": screws.id, "quantity": 4}])
        data = line.tectora_get_supplier_products()
        self.assertEqual(len(data["stock"]), 1)
        group = data["stock"][0]
        picking = self.env["stock.picking"].browse(group["id"])
        self.assertEqual(picking.picking_type_id.code, "outgoing")
        move = picking.move_ids
        self.assertEqual(move.product_id, screws)
        self.assertEqual(move.product_uom_qty, 4)
        self.assertEqual(move.state, "assigned", "the stock is reserved")
        self.assertEqual(screws.with_company(self.env.company).free_qty, 6)
        # A second delivery from stock goes on the same open delivery.
        line.action_tectora_deliver_from_stock([{"product_id": screws.id, "quantity": 2}])
        self.assertEqual(len(picking.move_ids), 2)
        service = self.env["product.product"].create({
            "name": "Kraanhuur", "type": "service", "purchase_ok": True,
        })
        with self.assertRaises(UserError, msg="only stocked products come from the warehouse"):
            line.action_tectora_deliver_from_stock([{"product_id": service.id, "quantity": 1}])

        # A cancelled order puts its products back on top.
        purchase.button_cancel()
        line.product_line_ids.invalidate_recordset(["source"])
        data = line.tectora_get_supplier_products()
        self.assertIn(self.product.id, [item["id"] for item in data["items"]])
        self.assertFalse(data["ordered"])

    def test_board_data_and_empty_configuration(self):
        project = self._project()
        data = project.tectora_get_order_list_data()
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            [s["name"] for s in data["lines"][0]["suppliers"]], ["Dakmaterialen NV", "Isolatie BV"]
        )
        self.env["tectora.order.list.template"].search([]).action_archive()
        empty = self._project()
        data = empty.tectora_get_order_list_data()
        self.assertEqual(data["total"], 0)
        self.assertFalse(data["project"]["can_create"])

    def test_copy_does_not_build_a_second_list(self):
        project = self._project()
        copy = project.copy()
        self.assertFalse(copy.tectora_order_line_ids)
        copy.action_tectora_create_order_list()
        self.assertEqual(len(copy.tectora_order_line_ids), 2)
        copy.action_tectora_create_order_list()
        self.assertEqual(len(copy.tectora_order_line_ids), 2)
