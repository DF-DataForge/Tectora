# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
    tectora_allows_objects = fields.Boolean(
        string="Voor dakobjecten",
        compute="_compute_tectora_allows_objects",
        store=True,
        help="Technisch veld: waar zodra 'Dakobjecten' bij de toepassingen "
        "staat. Bepaalt of het icoon voor de tekening gevraagd wordt.",
    )
    tectora_canvas_icon = fields.Image(
        string="Icoon op de tekening",
        max_width=256,
        max_height=256,
        help="Wordt op de tekening in het dakobject getoond, zodat een "
        "schoorsteen, koepel of HVAC-unit op het plan te onderscheiden is. "
        "Het icoon van het eerste toegewezen product van deze categorie "
        "wordt gebruikt. Vierkant en met een transparante achtergrond komt "
        "het best uit.",
    )

    @api.depends("tectora_usage_ids", "tectora_usage_ids.code")
    def _compute_tectora_allows_objects(self):
        for category in self:
            category.tectora_allows_objects = "object" in category.tectora_usage_ids.mapped(
                "code"
            )
