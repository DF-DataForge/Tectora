# -*- coding: utf-8 -*-
from odoo import fields, models


class TectoraProjectPhase(models.Model):
    """A phase of the task follow-up. Every project gets one milestone per
    phase; the tasks of the phase hang on that milestone."""

    _name = "tectora.project.phase"
    _description = "Projectfase"
    _order = "sequence, id"

    name = fields.Char(string="Fase", required=True, translate=True)
    subtitle = fields.Char(
        string="Omschrijving", translate=True,
        help="Korte toelichting, bv. 'vóór goedkeuring'.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    task_template_ids = fields.One2many(
        "tectora.task.template", "phase_id", string="Taaksjablonen"
    )
    deadline_reference = fields.Selection(
        [("start", "Startdatum project"), ("end", "Einddatum project")],
        string="Deadline mijlpaal t.o.v.",
        help="De deadline van de mijlpaal wordt berekend op basis van deze projectdatum.",
    )
    deadline_offset = fields.Integer(
        string="Dagen", help="Negatief = vóór de referentiedatum."
    )
