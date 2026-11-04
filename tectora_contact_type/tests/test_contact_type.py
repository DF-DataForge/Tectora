# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestContactType(TransactionCase):

    def test_contact_type_values_and_grouping(self):
        Partner = self.env["res.partner"]
        selection = dict(Partner._fields["df_cont_type"]._description_selection(self.env))
        self.assertEqual(list(selection.values()), [
            "Particulieren", "Energiehuizen", "Bouwonderneming", "Architect",
            "Syndicus", "Niet particulieren", "Steden en gemeentes",
        ])
        architect = Partner.create({"name": "Studio Dak", "df_cont_type": "architect"})
        self.assertIn(architect, Partner.search([("df_cont_type", "=", "architect")]))
        groups = Partner._read_group([("id", "=", architect.id)], ["df_cont_type"], ["__count"])
        self.assertEqual(groups, [("architect", 1)])
