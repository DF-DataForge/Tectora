# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    tectora_usage_ids = fields.Many2many(
        "tectora.roof.usage",
        "product_category_tectora_usage_rel",
        "category_id",
        "usage_id",
        string="Kan gebruikt worden voor",
        help="Bepaalt waar de producten van deze categorie in de "
        "Dakmeting-app aangeboden worden: enkel bij de gekozen doelen "
        "(dakobject, rand, oppervlak, hoek). Zonder waarde verschijnt de "
        "categorie nergens in de toewijzingsdialoog van de tekening.",
    )
