# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    """Order lines mirror the roof project.

    A chapter line (Algemene werken, Veiligheid, Afbraak, Opbouw, ...) is tied
    one-to-one to a project-level product line of the roof project; the
    measurement lines (per roof section and roof object) are rebuilt from the
    drawing. Either way the quantities on the quotation follow the roof
    project's calculations.
    """

    _inherit = "sale.order.line"

    roof_line_id = fields.Many2one(
        "tectora.roof.section.product",
        string="Projectlijn dakmeting",
        ondelete="set null",
        copy=False,
        index=True,
        help="Lijn op het dakproject waarvan deze offertelijn de spiegel is; "
        "de hoeveelheid volgt de meting.",
    )
    roof_measurement_line = fields.Boolean(
        string="Meetlijn",
        copy=False,
        help="Aangemaakt uit de daksecties en dakobjecten van de meting; wordt "
        "herbouwd zodra de tekening verandert.",
    )
    # The estimate of the line: quantity x the product's hours per unit, one
    # figure per work kind, so the order can total demolition and execution
    # apart and size a task for each.
    tectora_execution_hours = fields.Float(
        string="Uren opbouw",
        compute="_compute_tectora_hours",
        store=True,
        digits=(16, 2),
        help="Hoeveelheid × uren opbouw per eenheid van het product.",
    )
    tectora_demolition_hours = fields.Float(
        string="Uren afbraak",
        compute="_compute_tectora_hours",
        store=True,
        digits=(16, 2),
        help="Hoeveelheid × uren afbraak per eenheid van het product.",
    )
    tectora_estimated_hours = fields.Float(
        string="Geschatte tijd",
        compute="_compute_tectora_hours",
        store=True,
        digits=(16, 2),
        help="Uren opbouw en afbraak van deze lijn samen.",
    )

    @api.depends(
        "product_id.tectora_hours_execution_per_uom",
        "product_id.tectora_hours_demolition_per_uom",
        "product_uom_qty",
        "product_uom_id",
        "display_type",
    )
    def _compute_tectora_hours(self):
        for line in self:
            product = line.product_id
            if line.display_type or not product or not line.product_uom_qty:
                line.tectora_execution_hours = 0.0
                line.tectora_demolition_hours = 0.0
                line.tectora_estimated_hours = 0.0
                continue
            quantity = line._tectora_quantity_in_product_uom()
            line.tectora_execution_hours = (
                quantity * product.tectora_hours_execution_per_uom
            )
            line.tectora_demolition_hours = (
                quantity * product.tectora_hours_demolition_per_uom
            )
            line.tectora_estimated_hours = (
                line.tectora_execution_hours + line.tectora_demolition_hours
            )

    def _tectora_quantity_in_product_uom(self):
        """The line's quantity in the product's own unit: the norm is per
        unit of the product, and a line may be sold in another one."""
        self.ensure_one()
        quantity = self.product_uom_qty
        product_uom = self.product_id.uom_id
        if self.product_uom_id and product_uom and self.product_uom_id != product_uom:
            quantity = self.product_uom_id._compute_quantity(quantity, product_uom)
        return quantity

    def _tectora_hours_of_kind(self, kind):
        """Hours of one work kind (``afbraak`` / ``uitvoering``) on the line."""
        self.ensure_one()
        if kind == "afbraak":
            return self.tectora_demolition_hours
        return self.tectora_execution_hours

    def _tectora_norm_of_kind(self, kind):
        """The product's hours per unit of one work kind."""
        self.ensure_one()
        if kind == "afbraak":
            return self.product_id.tectora_hours_demolition_per_uom
        return self.product_id.tectora_hours_execution_per_uom

    def _tectora_mirrorable(self):
        """Lines the roof project should know about: real product lines of an
        open quotation with a roof project, other than the measurement lines."""
        return self.filtered(
            lambda line: not line.display_type
            and line.product_id
            and not line.roof_measurement_line
            and not line.is_downpayment
            and line.order_id.roof_project_id
            and line.order_id.state in ("draft", "sent")
        )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get("tectora_sync"):
            for order in lines._tectora_mirrorable().order_id:
                order._tectora_mirror_to_roof(lines.filtered(lambda l: l.order_id == order))
        lines.order_id._tectora_sync_execution_task()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"product_uom_qty", "product_id", "product_uom_id"} & set(vals):
            if not self.env.context.get("tectora_sync"):
                for order in self._tectora_mirrorable().order_id:
                    order._tectora_mirror_to_roof(
                        self.filtered(lambda l: l.order_id == order)
                    )
            # A quantity changed on a confirmed order: the execution task
            # follows the new estimate.
            self.order_id._tectora_sync_execution_task()
        return result

    def unlink(self):
        """Removing a chapter line from the quotation removes it from the roof
        project too (measurement lines come back from the drawing)."""
        roof_lines = self.env["tectora.roof.section.product"]
        if not self.env.context.get("tectora_sync"):
            roof_lines = self._tectora_mirrorable().roof_line_id.filtered(
                "project_direct_id"
            )
        result = super().unlink()
        # After the order lines are gone: a roof line's own unlink removes
        # its order lines, which would take these out from under us.
        roof_lines = roof_lines.exists()
        if roof_lines:
            roof_lines.with_context(tectora_sync=True).unlink()
        return result
