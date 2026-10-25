# -*- coding: utf-8 -*-
from odoo import fields, models

ORDER_ACTIONS = [
    ("order", "Bestellen"),
    ("stock_first", "Stock eerst"),
]


class TectoraOrderListTemplate(models.Model):
    """A standard part of the order list: every new project gets one order
    list line per part."""

    _name = "tectora.order.list.template"
    _description = "Bestellijst: standaardonderdeel"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Onderdeel", required=True, translate=True)
    order_action = fields.Selection(
        ORDER_ACTIONS, string="Actie", required=True, default="order",
        help="Bestellen: altijd een bestelling voor dit project.\n"
        "Stock eerst: eerst de stock controleren; enkel het tekort bestellen.",
    )
    supplier_note = fields.Text(string="Leveranciers (volgens bestellijst)", translate=True)
    partner_ids = fields.Many2many(
        "res.partner", string="Leveranciers", domain=[("parent_id", "=", False)],
        help="Voorgestelde leveranciers; de eerste wordt standaard gekozen.",
    )
    active = fields.Boolean(default=True)
