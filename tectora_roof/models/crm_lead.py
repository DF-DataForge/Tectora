# -*- coding: utf-8 -*-
from odoo import _, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    roof_project_ids = fields.One2many(
        "tectora.roof.project", "opportunity_id", string="Dakprojecten"
    )
    roof_project_count = fields.Integer(compute="_compute_roof_project_count")

    def _compute_roof_project_count(self):
        for lead in self:
            lead.roof_project_count = len(lead.roof_project_ids)

    def _tectora_ensure_customer(self):
        """An opportunity that has contact details (a web request: name,
        email, address) but no customer gets one: the existing contact with
        that email, else a new contact made from the opportunity. So the
        quotation and the roof project made from it have their customer.
        Without any contact details nothing is guessed."""
        for lead in self.filtered(lambda lead: not lead.partner_id):
            partner = lead._find_matching_partner()
            if partner:
                lead.partner_id = partner
            elif lead.contact_name or lead.partner_name or lead.email_from:
                lead._handle_partner_assignment(create_missing=True)

    def action_sale_quotations_new(self):
        # Odoo asks who the customer is when the opportunity has none; with
        # contact details on it, the customer is linked straight away.
        self._tectora_ensure_customer()
        return super().action_sale_quotations_new()

    def action_create_roof_project(self):
        """Create a roof measurement project prefilled from the opportunity."""
        self.ensure_one()
        self._tectora_ensure_customer()
        street = " ".join(filter(None, [self.street, self.street2]))
        locality = " ".join(filter(None, [self.zip, self.city]))
        address = ", ".join(filter(None, [street, locality]))
        project = self.env["tectora.roof.project"].create(
            {
                "name": self.name,
                "partner_id": self.partner_id.id or False,
                "opportunity_id": self.id,
                "address": address or False,
                "company_id": self.company_id.id or self.env.company.id,
            }
        )
        self.message_post(
            body=_("Dakproject %s aangemaakt.", project._get_html_link())
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": project.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_roof_projects(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Dakprojecten"),
            "res_model": "tectora.roof.project",
            "view_mode": "list,form",
            "domain": [("opportunity_id", "=", self.id)],
            "context": {
                "default_opportunity_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }
        if self.roof_project_count == 1:
            action.update(
                {"view_mode": "form", "res_id": self.roof_project_ids.id, "domain": []}
            )
        return action
