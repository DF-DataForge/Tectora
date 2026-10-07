# -*- coding: utf-8 -*-
from odoo import api, fields, models

PROJECT_TYPES = [
    ("renovatie", "Renovatie"),
    ("nieuwbouw", "Nieuwbouw"),
    ("industrie", "Industrie"),
]


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    tectora_project_type = fields.Selection(
        PROJECT_TYPES,
        string="Projecttype",
        compute="_compute_tectora_project_type",
        store=True,
        readonly=False,
        help="Wordt het projecttype (en de prijslijst) van een offerte die met "
        "dit sjabloon begint. Afgeleid uit de naam (\"Renovatie ...\", "
        "\"Nieuwbouw ...\") of, zonder type in de naam, uit de secties: een "
        "sjabloon met afbouwwerken is renovatie.",
    )

    @api.depends("name", "sale_order_template_line_ids.name")
    def _compute_tectora_project_type(self):
        for template in self:
            name = (template.name or "").strip().lower()
            kind = next((key for key, _label in PROJECT_TYPES if name.startswith(key)), False)
            if not kind:
                headers = template.sale_order_template_line_ids.filtered(
                    lambda line: line.display_type == "line_section"
                ).mapped(lambda line: (line.name or "").lower())
                if any("afbouw" in header or "afbraak" in header for header in headers):
                    kind = "renovatie"
                elif any("opbouw" in header for header in headers):
                    kind = "nieuwbouw"
            template.tectora_project_type = kind or template.tectora_project_type
