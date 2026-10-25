# -*- coding: utf-8 -*-
from odoo import fields, models


class TectoraTaskTemplate(models.Model):
    _inherit = "tectora.task.template"

    order_list_auto = fields.Boolean(
        string="Bestellijst afgevinkt (automatisch)",
        help="De taak wordt automatisch afgevinkt zodra de bestellijst van "
        "het project volledig afgevinkt is, en terug opengezet als dat niet "
        "meer zo is. Op de takenpagina linkt ze naar de bestellijst.",
    )
