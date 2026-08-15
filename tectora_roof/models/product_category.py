# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    tectora_usage = fields.Selection(
        [
            ("object", "Dakobjecten"),
            ("edge", "Randen"),
            ("surface", "Oppervlaktes"),
        ],
        string="Kan gebruikt worden voor",
        help="Indien ingevuld kunnen de producten in deze categorie in de "
        "Dakmeting-app enkel gekoppeld worden aan het gekozen doel: een "
        "dakobject, een rand (zijde) of een oppervlak. Leeg gelaten zijn de "
        "producten overal bruikbaar.",
    )
