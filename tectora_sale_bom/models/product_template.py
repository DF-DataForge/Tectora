# -*- coding: utf-8 -*-
from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        result = super().write(vals)
        if {"tectora_recalc", "tectora_recalc_uom"} & vals.keys():
            self._tectora_sync_recalc_uom()
        return result

    def _tectora_sync_recalc_uom(self):
        """Hercalculatie switched on or another Reken-UoM: the bills of
        materials count the component in that unit from now on. The
        quantities stay; they already were in the Reken-UoM."""
        templates = self.filtered("tectora_recalc")
        if not templates:
            return
        products = templates.product_variant_ids
        self.env["mrp.bom.line"].search(
            [("product_id", "in", products.ids)]
        )._tectora_apply_recalc_uom()
        self.env["tectora.sale.bom.line"].search([
            ("product_id", "in", products.ids),
            ("bom_id.order_id.state", "!=", "cancel"),
        ])._tectora_apply_recalc_uom()
