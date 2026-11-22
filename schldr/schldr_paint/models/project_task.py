# -*- coding: utf-8 -*-
from odoo import fields, models

# The two tasks a confirmed order sizes on its project, so hours can be
# logged on preparation and on painting separately.
WORK_KINDS = [
    ("voorbereiding", "Voorbereiding"),
    ("uitvoering", "Schilderwerken"),
]


class ProjectTask(models.Model):
    _inherit = "project.task"

    schldr_work_kind = fields.Selection(
        WORK_KINDS,
        string="Werksoort (Schldr)",
        copy=False,
        index=True,
        help="De taak Voorbereiding of Schilderwerken van het project: haar "
        "toegewezen tijd volgt de geschatte tijd van de bevestigde order "
        "voor die werksoort (hoeveelheid × geschatte tijd per eenheid van "
        "elk product). Uren worden op deze taken gelogd, zodat voorbereiding "
        "en schilderen uit elkaar te houden zijn.",
    )
