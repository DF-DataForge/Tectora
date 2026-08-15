# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofObject(models.Model):
    _name = "tectora.roof.object"
    _description = "Roof Object (Chimney/Skylight)"
    _order = "project_id, id"

    name = fields.Char(string="Naam", required=True)
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Project",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    object_type = fields.Selection(
        [
            ("chimney", "Schoorsteen"),
            ("skylight", "Koepel / lichtstraat"),
            ("hvac", "HVAC-unit"),
            ("other", "Overig"),
        ],
        string="Type",
        required=True,
        default="chimney",
    )
    canvas_ref = fields.Char(string="Canvas ID", readonly=True, copy=False)
    width = fields.Float(string="Breedte (m)", digits=(16, 2))
    length = fields.Float(string="Lengte (m)", digits=(16, 2))
    height = fields.Float(string="Hoogte (m)", digits=(16, 2))
    area = fields.Float(string="Oppervlakte (m²)", digits=(16, 2))
    perimeter = fields.Float(string="Omtrek (m)", digits=(16, 2))
    volume = fields.Float(
        string="Volume (m³)",
        compute="_compute_volume",
        store=True,
        digits=(16, 3),
    )
    description = fields.Text(string="Omschrijving")

    @api.depends("area", "height")
    def _compute_volume(self):
        for record in self:
            record.volume = record.area * record.height
