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

    def _tectora_site_partner(self, address):
        """The contact of the site of this opportunity: its customer when the
        opportunity's address is the customer's (or empty), else a new
        delivery address under the customer. None without a customer."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return self.env["res.partner"]
        if not address or address == partner._tectora_one_line_address():
            return partner
        return self.env["res.partner"].create({
            "parent_id": partner.commercial_partner_id.id,
            "type": "delivery",
            "street": self.street,
            "street2": self.street2,
            "zip": self.zip,
            "city": self.city,
            "state_id": self.state_id.id,
            "country_id": self.country_id.id or partner.country_id.id,
        })

    def action_create_roof_project(self):
        """Create a roof measurement project prefilled from the opportunity."""
        self.ensure_one()
        street = " ".join(filter(None, [self.street, self.street2]))
        locality = " ".join(filter(None, [self.zip, self.city]))
        address = ", ".join(filter(None, [street, locality]))
        project = self.env["tectora.roof.project"].create(
            {
                "name": self.name,
                "partner_id": self.partner_id.id or False,
                "opportunity_id": self.id,
                "site_partner_id": self._tectora_site_partner(address).id or False,
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
