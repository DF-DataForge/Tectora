# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    df_cont_type = fields.Selection(
        [
            ("particulier", "Particulieren"),
            ("energiehuis", "Energiehuizen"),
            ("bouwonderneming", "Bouwonderneming"),
            ("architect", "Architect"),
            ("syndicus", "Syndicus"),
            ("niet_particulier", "Niet particulieren"),
            ("stad_gemeente", "Steden en gemeentes"),
        ],
        string="Contacttype",
        tracking=True,
        help="Deelt de contacten in: particulieren, architecten, syndici, ...",
    )
