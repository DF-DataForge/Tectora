# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tectora_minutes_per_uom = fields.Float(
        string="Geschatte tijd per eenheid",
        digits=(16, 1),
        help="Uitvoeringstijd in minuten per verkochte eenheid van dit product "
        "(per m², per lm, per stuk). Elke offertelijn rekent er haar "
        "geschatte tijd mee uit; de som komt op de offerte en, bij "
        "bevestiging, als toegewezen tijd op de taak Uitvoeringswerken "
        "van het project.",
    )
