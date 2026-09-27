# -*- coding: utf-8 -*-
from odoo import fields, models


class TectoraRoofUsage(models.Model):
    _name = "tectora.roof.usage"
    _description = "Dakmeting toepassing"
    _order = "sequence, id"

    name = fields.Char(string="Naam", required=True)
    code = fields.Char(
        string="Code",
        required=True,
        help="Technical code the canvas uses when filtering products: "
        "object, edge, surface, corner, corner_inner, corner_outer or seam "
        "(a naad between two roof surfaces).",
    )
    sequence = fields.Integer(default=10)
