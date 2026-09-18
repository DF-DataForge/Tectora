# -*- coding: utf-8 -*-
from odoo import fields, models

# The two tasks a confirmed order sizes on its project, so hours can be
# logged on demolition and on execution separately.
WORK_KINDS = [
    ("afbraak", "Afbraakwerken"),
    ("uitvoering", "Uitvoeringswerken"),
]


class ProjectTask(models.Model):
    _inherit = "project.task"

    tectora_work_kind = fields.Selection(
        WORK_KINDS,
        string="Werksoort (Tectora)",
        copy=False,
        index=True,
        help="De taak Afbraakwerken of Uitvoeringswerken van het project: haar "
        "toegewezen tijd volgt de geschatte tijd van de bevestigde order "
        "voor die werksoort (hoeveelheid × geschatte tijd per eenheid van "
        "elk product). Uren worden op deze taken gelogd, zodat afbraak en "
        "uitvoering uit elkaar te houden zijn.",
    )
