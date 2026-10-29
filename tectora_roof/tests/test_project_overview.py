# -*- coding: utf-8 -*-
"""The projects overview: status and money over the projects of the roof
projects, and the projects behind every figure."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectOverview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Project = cls.env["project.project"]
        cls.customer = cls.env["res.partner"].create({"name": "Dhr. Peeters"})
        cls.service = cls.env["product.product"].create({
            "name": "Plaatsen EPDM", "type": "service", "list_price": 50,
        })

    def _confirmed_project(self, **roof_values):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 2})],
        })
        order.action_confirm()
        if roof_values:
            order.roof_project_id.write(roof_values)
        return order.roof_project_id.project_id

    def _tile(self, data, group, key):
        return next(tile for tile in data[group] if tile["key"] == key)

    def test_status_and_money(self):
        now = fields.Datetime.now()
        running = self._confirmed_project(
            planned_date_begin=now - timedelta(days=1), planned_date_end=now + timedelta(days=2),
        )
        soon = self._confirmed_project(
            planned_date_begin=now + timedelta(days=3), planned_date_end=now + timedelta(days=4),
        )
        unplanned = self._confirmed_project()
        late = self._confirmed_project(
            planned_date_begin=now - timedelta(days=9), planned_date_end=now - timedelta(days=8),
        )
        done = self._confirmed_project()
        done.roof_project_id.state = "done"

        data = self.Project.tectora_get_overview_data()
        tiles = {tile["key"]: set(tile["ids"]) for tile in data["status_tiles"]}
        self.assertIn(running.id, tiles["running"])
        self.assertIn(soon.id, tiles["planned"])
        self.assertIn(unplanned.id, tiles["unplanned"])
        self.assertIn(late.id, tiles["overdue"])
        self.assertIn(done.id, tiles["done"])
        self.assertNotIn(done.id, tiles["active"])
        self.assertTrue({running.id, soon.id, unplanned.id, late.id} <= tiles["active"])

        soon_list = next(entry for entry in data["lists"] if entry["key"] == "soon")
        self.assertIn(soon.id, [item["id"] for item in soon_list["items"]])
        revenue = self._tile(data, "money_tiles", "revenue")
        self.assertIn(running.id, revenue["ids"], "a confirmed order counts in the order value")
        self.assertTrue(revenue["value"])

    def test_figures_open_their_projects(self):
        project = self._confirmed_project()
        action = self.Project.action_tectora_overview_open_projects([project.id], "Gepland")
        self.assertEqual(action["res_model"], "project.project")
        self.assertEqual(action["name"], "Gepland")
        self.assertEqual(action["domain"], [("id", "in", [project.id])])
        dashboard = project.action_open_dashboard()
        self.assertEqual(dashboard["res_id"], project.id)

    def test_batch_totals_match_single(self):
        first, second = self._confirmed_project(), self._confirmed_project()
        batch = (first | second)._tectora_profitability_by_project()
        for project in (first, second):
            self.assertEqual(batch.get(project.id, {}), project._tectora_profitability_totals())
