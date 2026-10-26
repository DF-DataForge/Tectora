# -*- coding: utf-8 -*-
from odoo import api, fields, models

LEGACY_INVOICED = [
    ("no", "Niet gefactureerd"),
    ("partial", "Deels gefactureerd"),
    ("invoiced", "Volledig gefactureerd"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    tectora_legacy_number = fields.Char(
        string="Offertenummer oud systeem",
        copy=False,
        index=True,
        readonly=True,
        help="Nummer van de offerte in het oude systeem (Simpla); een nieuwe "
        "import slaat offertes met een gekend nummer over of werkt hun status bij.",
    )
    tectora_legacy_status = fields.Char(
        string="Status oud systeem", copy=False, readonly=True,
    )
    tectora_legacy_invoiced = fields.Selection(
        LEGACY_INVOICED,
        string="Facturatie oud systeem",
        copy=False,
        readonly=True,
        help="Volledig gefactureerd: de facturen staan in het oude systeem; "
        "de order telt in Odoo als gefactureerd.",
    )

    def _tectora_on_confirm(self):
        # An imported order of a finished site gets no roof project/project.
        if self.env.context.get("tectora_import_no_project"):
            return
        return super()._tectora_on_confirm()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _tectora_legacy_invoiced(self):
        return self.filtered(
            lambda line: line.order_id.tectora_legacy_invoiced == "invoiced"
            and not line.display_type
        )

    @api.depends("order_id.tectora_legacy_invoiced")
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self._tectora_legacy_invoiced():
            line.qty_to_invoice = 0.0

    @api.depends("order_id.tectora_legacy_invoiced")
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        for line in self._tectora_legacy_invoiced().filtered(lambda l: l.state == "sale"):
            line.invoice_status = "invoiced"

    @api.depends("order_id.tectora_legacy_invoiced")
    def _compute_untaxed_amount_to_invoice(self):
        super()._compute_untaxed_amount_to_invoice()
        for line in self._tectora_legacy_invoiced():
            line.untaxed_amount_to_invoice = 0.0
