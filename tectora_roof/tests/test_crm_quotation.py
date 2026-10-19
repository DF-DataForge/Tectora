# -*- coding: utf-8 -*-
"""A quotation or roof project made from an opportunity has its customer,
also when the opportunity only carries contact details (a web request)."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCrmQuotation(TransactionCase):

    def _lead(self, **values):
        return self.env["crm.lead"].create({"name": "Plat dak", "type": "opportunity", **values})

    def test_customer_made_from_contact_details(self):
        lead = self._lead(contact_name="Philippe Michiels", email_from="philippe@example.com")
        action = lead.action_sale_quotations_new()
        self.assertTrue(lead.partner_id)
        self.assertEqual(lead.partner_id.name, "Philippe Michiels")
        self.assertEqual(action["context"]["default_partner_id"], lead.partner_id.id)

    def test_existing_contact_is_reused(self):
        partner = self.env["res.partner"].create({"name": "Dhr. Michiels", "email": "michiels@example.com"})
        lead = self._lead(contact_name="Michiels", email_from="michiels@example.com")
        lead.action_sale_quotations_new()
        self.assertEqual(lead.partner_id, partner)

    def test_customer_on_the_roof_project(self):
        lead = self._lead(contact_name="Familie Peeters", email_from="peeters@example.com")
        action = lead.action_create_roof_project()
        roof = self.env["tectora.roof.project"].browse(action["res_id"])
        self.assertEqual(roof.partner_id, lead.partner_id)
        self.assertTrue(roof.partner_id)

    def test_nothing_to_go_on_asks(self):
        lead = self._lead()
        action = lead.action_sale_quotations_new()
        self.assertFalse(lead.partner_id)
        self.assertEqual(action["res_model"], "crm.quotation.partner")
