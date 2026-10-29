# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TectoraRoofMaterial(models.Model):
    _inherit = "tectora.roof.material"

    order_list_move_id = fields.Many2one(
        "stock.move",
        string="Levering uit magazijn",
        readonly=True,
        copy=False,
        ondelete="set null",
        index=True,
        help="De beweging waarmee de bestellijst dit materiaal uit het "
        "magazijn naar de werf stuurt.",
    )

    @api.depends("order_list_move_id.state")
    def _compute_purchase_state(self):
        super()._compute_purchase_state()
        for line in self:
            move = line.order_list_move_id
            if line.purchase_state == "to_order" and move and move.state != "cancel":
                line.purchase_state = "stock"

    @api.depends("order_list_move_id.state", "order_list_move_id.picking_id")
    def _compute_pickings(self):
        super()._compute_pickings()
        for line in self:
            move = line.order_list_move_id
            if not line.picking_ids and move and move.state != "cancel" and move.picking_id:
                line.picking_ids = move.picking_id
                line.picking_id = move.picking_id
