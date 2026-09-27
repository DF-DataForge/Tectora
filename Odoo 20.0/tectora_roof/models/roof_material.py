# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofMaterial(models.Model):
    _name = "tectora.roof.material"
    _description = "Roof Project Material Requirement"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id")
    product_id = fields.Many2one(
        "product.product", string="Materiaal", required=True, index=True
    )
    product_uom_id = fields.Many2one("uom.uom", string="Eenheid")
    quantity = fields.Float(
        string="Benodigde hoeveelheid", digits="Product Unit of Measure"
    )
    source_product_id = fields.Many2one(
        "product.product",
        string="Uit verkoopproduct",
        help="The sold product this material requirement was exploded from.",
    )
    bom_name = fields.Char(
        string="Stuklijst",
        help="Name of the bill of materials the requirement comes from; empty "
        "when the sold product has no bill of materials and is itself the "
        "material.",
    )
    sale_order_id = fields.Many2one(
        "sale.order", string="Verkooporder", index=True, ondelete="cascade"
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line", string="Orderlijn", ondelete="cascade"
    )
    unit_cost = fields.Float(
        string="Kostprijs/eenheid", compute="_compute_costs", digits="Product Price"
    )
    cost_subtotal = fields.Monetary(
        string="Kost",
        compute="_compute_costs",
        store=True,
        currency_field="currency_id",
    )
    notes = fields.Char(string="Notities")

    @api.depends("quantity", "product_id.standard_price")
    def _compute_costs(self):
        for line in self:
            line.unit_cost = line.product_id.standard_price
            line.cost_subtotal = line.quantity * line.product_id.standard_price
