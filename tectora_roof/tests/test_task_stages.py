# -*- coding: utf-8 -*-
"""The projects of confirmed orders share one set of task stages instead of
four new stages each (Odoo 20's default for a new project)."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTaskStages(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.customer = cls.env["res.partner"].create({"name": "Dhr. Peeters"})
        cls.service = cls.env["product.product"].create({
            "name": "Plaatsen EPDM", "type": "service", "list_price": 50,
        })

    def _confirmed_project(self):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.service.id, "product_uom_qty": 2})],
        })
        order.action_confirm()
        return order.roof_project_id.project_id

    def test_projects_share_the_stages(self):
        stages_before = self.env["project.task.type"].search_count([])
        first = self._confirmed_project()
        second = self._confirmed_project()
        self.assertTrue(first and second and first != second)
        expected = [
            self.env.ref("tectora_roof.project_task_type_%s" % key)
            for key in ("nieuw", "bezig", "klaar", "geannuleerd")
        ]
        self.assertEqual(first.type_ids.sorted("sequence").ids, [s.id for s in expected])
        self.assertEqual(second.type_ids, first.type_ids)
        self.assertEqual(self.env["project.task.type"].search_count([]), stages_before)
        self.assertEqual(expected[0].with_context(lang="en_US").name, "Nieuw")
        self.assertTrue(expected[-1].fold)
