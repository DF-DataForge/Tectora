# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    tectora_title_id = fields.Many2one(
        "tectora.partner.title", string="Aanspreektitel", ondelete="restrict"
    )
    lead_connector_log_ids = fields.One2many(
        "tectora.lead.connector.log", "lead_id", string="Leadconnector"
    )

    def _prepare_customer_values(self, partner_name, parent_id=False):
        values = super()._prepare_customer_values(partner_name, parent_id=parent_id)
        # the contact created from the lead is the person the salutation is for
        if self.tectora_title_id:
            values["tectora_title_id"] = self.tectora_title_id.id
        return values
