# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # One2many for the ownership (copied with the line, gone with it); a line
    # has at most one, see tectora_sale_bom_id.
    tectora_sale_bom_ids = fields.One2many(
        "tectora.sale.bom", "sale_line_id", copy=True
    )
    tectora_sale_bom_id = fields.Many2one(
        "tectora.sale.bom",
        string="Stuklijst op maat",
        compute="_compute_tectora_sale_bom_id",
    )
    tectora_has_sale_bom = fields.Boolean(
        string="Heeft stuklijst op maat",
        compute="_compute_tectora_sale_bom_id",
        help="De componenten van deze lijn werden op de offerte aangepast; ze "
        "vervangen de stuklijst van het product.",
    )

    @api.depends("tectora_sale_bom_ids")
    def _compute_tectora_sale_bom_id(self):
        for line in self:
            line.tectora_sale_bom_id = line.tectora_sale_bom_ids[:1]
            line.tectora_has_sale_bom = bool(line.tectora_sale_bom_ids)

    def _tectora_sale_bom_line_values(self, bom):
        """The components of ``bom`` per unit of the product, in the
        product's unit, as lines of a bill of materials made to measure."""
        self.ensure_one()
        product = self.product_id
        per = bom.product_uom_id._compute_quantity(
            bom.product_qty or 1.0, product.uom_id, round=False
        ) or 1.0
        values = []
        for bom_line in bom.bom_line_ids:
            if bom_line._skip_bom_line(product):
                continue
            fixed = bom_line.tectora_fixed_qty
            values.append({
                "sequence": bom_line.sequence,
                "product_id": bom_line.product_id.id,
                "product_uom_id": bom_line.product_uom_id.id,
                "quantity": bom_line.product_qty if fixed else bom_line.product_qty / per,
                "fixed_quantity": fixed,
            })
        return values

    def action_open_tectora_sale_bom(self):
        """The bill of materials of this line, to adapt for this quotation.

        The first time, the dialog is filled from the product's bill of
        materials (or empty when it has none) and nothing is stored until it
        is saved, so closing it leaves the line on the product's stuklijst.
        """
        self.ensure_one()
        if not self.product_id or self.display_type:
            raise UserError(_("Kies eerst een product op de lijn."))
        view = self.env.ref("tectora_sale_bom.view_tectora_sale_bom_form")
        action = {
            "type": "ir.actions.act_window",
            "name": _("Stuklijst: %s", self.product_id.display_name),
            "res_model": "tectora.sale.bom",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }
        if self.tectora_sale_bom_id:
            action["res_id"] = self.tectora_sale_bom_id.id
            return action
        if self.order_id.state == "cancel":
            raise UserError(_("%s is geannuleerd.", self.order_id.name))
        bom = self.order_id._tectora_find_boms(self.product_id).get(self.product_id)
        lines = self._tectora_sale_bom_line_values(bom) if bom else []
        # The margin that keeps the line's current price, so opening and
        # saving changes nothing until a component does.
        draft = self.env["tectora.sale.bom"].new({
            "sale_line_id": self.id,
            "line_ids": [Command.create(values) for values in lines],
        })
        margin = draft._margin_for_price(draft.cost_per_unit, self.price_unit)
        action["context"] = {
            "default_sale_line_id": self.id,
            "default_source_bom_id": bom.id if bom else False,
            "default_margin_percent": margin,
            "default_line_ids": [Command.create(values) for values in lines],
        }
        return action
