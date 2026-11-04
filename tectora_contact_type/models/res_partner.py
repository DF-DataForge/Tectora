# -*- coding: utf-8 -*-
from odoo import fields, models

CONTACT_TYPES = [
    ("particulier", "Particulieren"),
    ("energiehuis", "Energiehuizen"),
    ("bouwonderneming", "Bouwonderneming"),
    ("architect", "Architect"),
    ("syndicus", "Syndicus"),
    ("niet_particulier", "Niet particulieren"),
    ("stad_gemeente", "Steden en gemeentes"),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    df_cont_type = fields.Selection(
        CONTACT_TYPES,
        string="Contacttype",
        tracking=True,
        help="Deelt de contacten in: particulieren, architecten, syndici, ...",
    )
