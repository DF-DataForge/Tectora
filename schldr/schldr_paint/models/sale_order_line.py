# -*- coding: utf-8 -*-
from odoo import api, fields, models


def label_without_reference(label, product):
    """The label of a quotation or invoice line as the customer reads it:
    without the product's internal reference ("[S00053] ") in front of a
    line, the way Odoo writes the product name into the line."""
    code = product.default_code
    if not label or not code:
        return label or ""
    prefix = "[%s]" % code
    return "\n".join(
        line[len(prefix):].lstrip() if line.startswith(prefix) else line
        for line in label.split("\n")
    )


class SaleOrderLine(models.Model):
    """Order lines that come from the plan of the painting project carry the
    key of what they stand for (a room, a surface group, a paint system and a
    colour), so a changed plan updates their quantity and leaves their price
    alone."""

    _inherit = "sale.order.line"

    def _schldr_report_label(self):
        """The line's label on the quotation PDF, without the reference."""
        self.ensure_one()
        return label_without_reference(self.label, self.product_id)

    schldr_line_id = fields.Many2one(
        "schldr.project.line",
        string="Algemene werken",
        ondelete="set null",
        copy=False,
        index=True,
        help="Lijn van de algemene werken op het schilderproject waarvan deze "
        "offertelijn de spiegel is.",
    )
    schldr_line_key = fields.Char(
        string="Sleutel uit het plan",
        copy=False,
        index=True,
        help="Waar deze lijn in het plan voor staat (ruimte, groep, "
        "verfsysteem, kleur). Zolang dat hetzelfde blijft, past een gewijzigd "
        "plan enkel de hoeveelheid aan.",
    )
    schldr_colour_id = fields.Many2one(
        "schldr.colour", string="Kleur", ondelete="set null", copy=False
    )
    schldr_measurement_line = fields.Boolean(
        string="Meetlijn",
        copy=False,
        help="Aangemaakt uit het plan; de hoeveelheid volgt de meting.",
    )
    # The estimate of the line: quantity x the product's hours per unit, one
    # figure per work kind, so the order can total preparation and painting
    # apart and size a task for each.
    schldr_execution_hours = fields.Float(
        string="Uren schilderen",
        compute="_compute_schldr_hours",
        store=True,
        digits=(16, 2),
        help="Hoeveelheid × uren schilderen per eenheid van het product.",
    )
    schldr_preparation_hours = fields.Float(
        string="Uren voorbereiding",
        compute="_compute_schldr_hours",
        store=True,
        digits=(16, 2),
        help="Hoeveelheid × uren voorbereiding per eenheid van het product.",
    )
    schldr_estimated_hours = fields.Float(
        string="Geschatte tijd",
        compute="_compute_schldr_hours",
        store=True,
        digits=(16, 2),
        help="Uren voorbereiding en schilderen van deze lijn samen.",
    )

    @api.depends(
        "product_id.schldr_hours_execution_per_uom",
        "product_id.schldr_hours_preparation_per_uom",
        "product_uom_qty",
        "product_uom_id",
        "display_type",
    )
    def _compute_schldr_hours(self):
        for line in self:
            product = line.product_id
            if line.display_type or not product or not line.product_uom_qty:
                line.schldr_execution_hours = 0.0
                line.schldr_preparation_hours = 0.0
                line.schldr_estimated_hours = 0.0
                continue
            quantity = line._schldr_quantity_in_product_uom()
            line.schldr_execution_hours = (
                quantity * product.schldr_hours_execution_per_uom
            )
            line.schldr_preparation_hours = (
                quantity * product.schldr_hours_preparation_per_uom
            )
            line.schldr_estimated_hours = (
                line.schldr_execution_hours + line.schldr_preparation_hours
            )

    def _schldr_quantity_in_product_uom(self):
        """The line's quantity in the product's own unit: the norm is per
        unit of the product, and a line may be sold in another one."""
        self.ensure_one()
        quantity = self.product_uom_qty
        product_uom = self.product_id.uom_id
        if self.product_uom_id and product_uom and self.product_uom_id != product_uom:
            quantity = self.product_uom_id._compute_quantity(quantity, product_uom)
        return quantity

    def _schldr_hours_of_kind(self, kind):
        """Hours of one work kind (``voorbereiding`` / ``uitvoering``) on the line."""
        self.ensure_one()
        if kind == "voorbereiding":
            return self.schldr_preparation_hours
        return self.schldr_execution_hours

    def _schldr_norm_of_kind(self, kind):
        """The product's hours per unit of one work kind."""
        self.ensure_one()
        if kind == "voorbereiding":
            return self.product_id.schldr_hours_preparation_per_uom
        return self.product_id.schldr_hours_execution_per_uom

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._schldr_sync_execution_task()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"product_uom_qty", "product_id", "product_uom_id"} & set(vals):
            # A quantity changed on a confirmed order: the tasks follow the
            # new estimate.
            self.order_id._schldr_sync_execution_task()
        return result
