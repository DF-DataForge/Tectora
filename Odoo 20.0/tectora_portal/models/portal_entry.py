# -*- coding: utf-8 -*-
from odoo import models


class PortalEntry(models.Model):
    _inherit = "portal.entry"

    def _filter_visible_portal_cards(self):
        """"Mijn werven" shows for every employee, also before a first site
        (as the config card it was up to Odoo 19); others see it only once
        the counter finds a site."""
        visible = super()._filter_visible_portal_cards()
        card = self.env.ref("tectora_portal.portal_entry_sites", raise_if_not_found=False)
        if card and card in self and self.env["hr.employee"].sudo().search_count(
            [("user_id", "=", self.env.uid)], limit=1
        ):
            visible |= card
        return visible
