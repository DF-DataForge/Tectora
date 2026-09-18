# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .project_task import WORK_KINDS


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
    tectora_minutes_per_uom = fields.Float(
        related="product_id.tectora_minutes_per_uom",
        string="Min. per eenheid",
    )
    tectora_estimated_hours = fields.Float(
        string="Geschatte tijd",
        compute="_compute_tectora_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Uitvoeringstijd in uren: hoeveelheid × geschatte tijd per eenheid "
        "van het product.",
    )
    tectora_work_kind = fields.Selection(
        WORK_KINDS,
        string="Werksoort",
        compute="_compute_tectora_work_kind",
        store=True,
        help="Afbraakwerken voor de producten van het hoofdstuk Afbraak, "
        "Uitvoeringswerken voor de rest. Bepaalt op welke taak van het "
        "project de geschatte tijd van deze lijn komt.",
    )

    @api.depends("product_id.categ_id.complete_name", "display_type")
    def _compute_tectora_work_kind(self):
        # The same reading of the category tree as the roof project's Afbraak
        # tab: the chapter "03. Afbraakwerken plat dak" and everything under it.
        for line in self:
            if line.display_type or not line.product_id:
                line.tectora_work_kind = False
                continue
            path = (line.product_id.categ_id.complete_name or "").lower()
            line.tectora_work_kind = "afbraak" if "afbraak" in path else "uitvoering"

    @api.depends(
        "product_id.tectora_minutes_per_uom",
        "product_uom_qty",
        "product_uom_id",
        "display_type",
    )
    def _compute_tectora_estimated_hours(self):
        for line in self:
            product = line.product_id
            minutes = product.tectora_minutes_per_uom if product else 0.0
            if line.display_type or not minutes or not line.product_uom_qty:
                line.tectora_estimated_hours = 0.0
                continue
            quantity = line.product_uom_qty
            # The norm is per unit of the product; a line sold in another unit
            # is converted first.
            if line.product_uom_id and line.product_uom_id != product.uom_id:
                quantity = line.product_uom_id._compute_quantity(
                    quantity, product.uom_id
                )
            line.tectora_estimated_hours = quantity * minutes / 60.0

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
        if not self.env.context.get("tectora_sync"):
            roof_lines = self._tectora_mirrorable().roof_line_id.filtered(
                "project_direct_id"
            )
            if roof_lines:
                roof_lines.with_context(tectora_sync=True).unlink()
        return super().unlink()
