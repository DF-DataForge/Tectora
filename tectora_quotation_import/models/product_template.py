# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tectora_description_label = fields.Boolean(
        string="Omschrijving als label",
        help="Op offertes, orders en facturen toont een lijn van dit product "
        "enkel haar omschrijving, niet de productnaam erboven. Voor de "
        "generieke werkposten (bv. 'Werkpost (oud systeem)') waarvan de "
        "omschrijving de eigenlijke werkpost is.",
    )
