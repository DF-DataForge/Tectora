# -*- coding: utf-8 -*-
from odoo import api, fields, models

PROJECT_TYPES = [
    ("renovatie", "Renovatie"),
    ("nieuwbouw", "Nieuwbouw"),
    ("industrie", "Industrie"),
]


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    schldr_project_type = fields.Selection(
        PROJECT_TYPES,
        string="Projecttype",
        compute="_compute_schldr_project_type",
        store=True,
        readonly=False,
        help="Wordt het projecttype (en de prijslijst) van een offerte die met "
        "dit sjabloon begint. Afgeleid uit de naam (\"Renovatie ...\", "
        "\"Nieuwbouw ...\").",
    )

    @api.depends("name")
    def _compute_schldr_project_type(self):
        for template in self:
            name = (template.name or "").strip().lower()
            kind = next((key for key, _label in PROJECT_TYPES if name.startswith(key)), False)
            template.schldr_project_type = kind or template.schldr_project_type
