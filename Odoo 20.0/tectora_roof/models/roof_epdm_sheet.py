# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofEpdmSheet(models.Model):
    _name = "tectora.roof.epdm.sheet"
    _description = "EPDM-doek"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Doek", compute="_compute_name", store=True, readonly=False
    )
    width = fields.Float(string="Breedte (m)", digits=(16, 2))
    length = fields.Float(string="Lengte (m)", digits=(16, 2))
    area = fields.Float(
        string="Oppervlakte (m²)", compute="_compute_area", store=True,
        digits=(16, 2),
    )
    dimensions = fields.Char(string="Afmeting", compute="_compute_dimensions")
    note = fields.Char(string="Notities")

    @api.depends("project_id.epdm_sheet_ids", "sequence")
    def _compute_name(self):
        for sheet in self:
            if sheet.name:
                continue
            siblings = sheet.project_id.epdm_sheet_ids
            index = list(siblings).index(sheet) + 1 if sheet in siblings else 1
            sheet.name = "EPDM doek %s" % index

    @api.depends("width", "length")
    def _compute_area(self):
        for sheet in self:
            sheet.area = sheet.width * sheet.length

    @api.depends("width", "length")
    def _compute_dimensions(self):
        for sheet in self:
            if sheet.width and sheet.length:
                sheet.dimensions = "%.2fm x %.2fm" % (sheet.width, sheet.length)
            else:
                sheet.dimensions = ""
