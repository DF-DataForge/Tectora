# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Two time norms per sold unit, because one works item can carry both: a
    # "leveren en plaatsen" post that first takes the old one down.
    tectora_hours_execution_per_uom = fields.Float(
        string="Uren opbouw per eenheid",
        digits=(16, 3),
        help="Uitvoeringstijd van de opbouwwerken in uren per verkochte eenheid "
        "van dit product (per m², per lm, per stuk); 0,25 is een kwartier. "
        "Elke offertelijn vermenigvuldigt dit met haar hoeveelheid; de som "
        "staat op de offerte en wordt bij bevestiging de toegewezen tijd van "
        "de taak Uitvoeringswerken van het project.",
    )
    tectora_hours_demolition_per_uom = fields.Float(
        string="Uren afbraak per eenheid",
        digits=(16, 3),
        help="Tijd van de afbraakwerken in uren per verkochte eenheid van dit "
        "product. Wordt op dezelfde manier gesommeerd en bij bevestiging de "
        "toegewezen tijd van de taak Afbraakwerken van het project.",
    )
