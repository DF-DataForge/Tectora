# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _tectora_description_only(self):
        return self.filtered(
            lambda line: line.product_id.tectora_description_label and line.name
        )

    @api.depends("product_id.tectora_description_label")
    def _compute_label(self):
        super()._compute_label()
        for line in self._tectora_description_only():
            line.label = line.name

    def _inverse_label(self):
        own = self.filtered(lambda line: line.product_id.tectora_description_label)
        for line in own:
            line.name = line.label
        super(AccountMoveLine, self - own)._inverse_label()
