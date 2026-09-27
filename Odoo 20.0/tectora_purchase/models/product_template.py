# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tectora_logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        help="Hoe dit materiaal geleverd wordt wanneer het uit de "
        "materiaalbehoefte besteld wordt: dropship naar de werf of levering "
        "aan het magazijn. Leeg: de route volgt de Odoo-routes van het "
        "product (Dropship), anders de standaardroute.",
    )
