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

    @api.depends("order_id.tectora_tax_id")
    def _compute_tax_ids(self):
        """One tax for the whole order when the order asks for it: every
        product line, including the ones the roof project adds later, takes
        the order's tax instead of the product's."""
        super()._compute_tax_ids()
        for line in self:
            tax = line.order_id.tectora_tax_id
            if tax and not line.display_type and line.product_id:
                line.tax_ids = tax

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
        return lines

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("tectora_sync") and (
            {"product_uom_qty", "product_id", "product_uom_id"} & set(vals)
        ):
            for order in self._tectora_mirrorable().order_id:
                order._tectora_mirror_to_roof(self.filtered(lambda l: l.order_id == order))
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
