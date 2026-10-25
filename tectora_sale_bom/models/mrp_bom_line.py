# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    tectora_fixed_qty = fields.Boolean(
        string="Vaste hoeveelheid",
        help="De hoeveelheid geldt per orderlijn en groeit niet mee met de "
        "verkochte hoeveelheid (één container per werf, niet per m²).",
    )

    # Hercalculatie: the quantity of a component with a Reken-UoM is in m,
    # m² or m³, whatever unit the line shows; this says how many pieces that
    # is, so the bill of materials is read right. The material list rounds
    # up per order line.
    tectora_recalc_info = fields.Char(
        string="Omrekening",
        compute="_compute_tectora_recalc_info",
        help="Het component heeft een hercalculatie: de hoeveelheid op deze "
        "lijn is in zijn Reken-UoM (m, m² of m³), per hoeveelheid van de "
        "stuklijst. Gedeeld door de maat van één stuk (L × B × H op het "
        "product) geeft dat het aantal stuks. De materiaallijst rondt per "
        "orderlijn naar boven af: 100 m² ÷ 0,72 m² = 138,89 → 139 stuks.",
    )

    @api.depends(
        "product_id", "product_qty",
        "product_id.tectora_recalc", "product_id.tectora_recalc_uom",
        "product_id.tectora_recalc_margin",
        "product_id.tectora_length", "product_id.tectora_width", "product_id.tectora_height",
    )
    def _compute_tectora_recalc_info(self):
        for line in self:
            template = line.product_id.product_tmpl_id
            line.tectora_recalc_info = (
                template._tectora_recalc_explanation(line.product_qty) if template else ""
            )

    # A component with hercalculatie is counted in its Reken-UoM (m, m² or
    # m³) on a bill of materials, so the line shows that unit, whatever the
    # unit the product is bought and stocked in.
    @api.onchange("product_id")
    def onchange_product_id(self):
        result = super().onchange_product_id()
        uom = self.product_id.product_tmpl_id._tectora_recalc_uom_record()
        if uom:
            self.uom_id = uom
        return result

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._tectora_apply_recalc_uom()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"product_id", "uom_id"} & vals.keys():
            self._tectora_apply_recalc_uom()
        return result

    def _tectora_apply_recalc_uom(self):
        """Put the lines of components with hercalculatie in the Reken-UoM."""
        for line in self:
            uom = line.product_id.product_tmpl_id._tectora_recalc_uom_record()
            if uom and line.uom_id != uom:
                line.uom_id = uom
