# -*- coding: utf-8 -*-
from odoo import api, models

from .sale_order_line import label_without_reference


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends("move_type", "partner_id", "partner_id.lang", "company_id")
    def _compute_narration(self):
        # Terms added as a PDF are printed on pages of their own, not in the
        # note of the invoice.
        super(AccountMove, self.filtered(lambda move: move.company_id.terms_type != "pdf"))._compute_narration()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _tectora_report_label(self):
        """The line's label on the invoice PDF, without the reference."""
        self.ensure_one()
        return label_without_reference(self.label, self.product_id)
