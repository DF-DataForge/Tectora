# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    tectora_execution = fields.Boolean(
        string="Uitvoeringstaak",
        copy=False,
        help="De taak Uitvoeringswerken van het project: haar toegewezen tijd "
        "volgt de geschatte uitvoeringstijd van de bevestigde order "
        "(hoeveelheid × geschatte tijd per eenheid van elk product).",
    )
