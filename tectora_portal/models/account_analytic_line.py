# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    tectora_timer_id = fields.Many2one(
        "tectora.roof.timer",
        string="Urenregistratie (portaal)",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
        help="De start/stop-registratie op het medewerkersportaal waaruit "
        "deze urenstaatlijn komt.",
    )
