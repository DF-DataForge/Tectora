# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraTaskTemplate(models.Model):
    """A task (or subtask) created on every project in its phase."""

    _name = "tectora.task.template"
    _description = "Taaksjabloon per projectfase"
    _order = "phase_sequence, sequence, id"
    _parent_store = True

    name = fields.Char(string="Taak", required=True, translate=True)
    sequence = fields.Integer(default=10)
    phase_id = fields.Many2one(
        "tectora.project.phase", string="Fase", required=True, ondelete="cascade"
    )
    phase_sequence = fields.Integer(
        related="phase_id.sequence", store=True, string="Volgorde fase"
    )
    parent_id = fields.Many2one(
        "tectora.task.template", string="Bovenliggende taak", ondelete="cascade",
        domain="[('parent_id', '=', False), ('phase_id', '=', phase_id)]",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("tectora.task.template", "parent_id", string="Subtaken")
    optional = fields.Boolean(
        string="Optie",
        help="Optionele taken staan standaard uit en worden per project aangezet.",
    )
    deadline_reference = fields.Selection(
        [("start", "Startdatum project"), ("end", "Einddatum project")],
        string="Deadline t.o.v.",
    )
    deadline_offset = fields.Integer(
        string="Dagen", help="Negatief = vóór de referentiedatum."
    )
    description = fields.Html(string="Toelichting", translate=True)
    active = fields.Boolean(default=True)

    @api.depends("name", "parent_id.name")
    def _compute_display_name(self):
        for template in self:
            template.display_name = (
                f"{template.parent_id.name} / {template.name}"
                if template.parent_id else template.name
            )
