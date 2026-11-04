# -*- coding: utf-8 -*-
"""The material list follows the order list: per product, where its order
stands (request for quotation, ordered, received) or its delivery from the
warehouse (waiting, reserved, delivered), computed live from the project's
order list, so it is always up to date."""
from odoo import api, fields, models

# From the least to the most advanced: a product ordered in two goes shows
# the step that is still behind.
ORDER_LIST_STATES = [
    ("none", "Niet op de bestellijst"),
    ("to_order", "Te bestellen"),
    ("rfq", "Prijsaanvraag"),
    ("stock_waiting", "Magazijn: wacht op voorraad"),
    ("ordered", "Besteld"),
    ("stock_reserved", "Magazijn: gereserveerd"),
    ("received", "Ontvangen"),
    ("stock_done", "Geleverd uit magazijn"),
]
STATE_RANK = {key: rank for rank, (key, _label) in enumerate(ORDER_LIST_STATES)}


class TectoraRoofMaterial(models.Model):
    _inherit = "tectora.roof.material"

    order_list_state = fields.Selection(
        ORDER_LIST_STATES,
        string="Bestellijst",
        compute="_compute_order_list_state",
        help="Waar dit product staat volgens de bestellijst van het project: "
        "besteld (prijsaanvraag, besteld, ontvangen) of uit het magazijn "
        "(wacht op voorraad, gereserveerd, geleverd). Bij twee bestellingen "
        "de stap die nog het verst achter staat.",
    )
    order_list_covered_qty = fields.Float(
        string="Voorzien via bestellijst",
        compute="_compute_order_list_state",
        digits="Product Unit",
        help="Besteld of uit het magazijn, in de eenheid van de materiaallijn.",
    )
    order_list_info = fields.Char(
        string="Bestellijst (detail)",
        compute="_compute_order_list_state",
        help="Bij welke leverancier en op welke aankooporder of levering.",
    )

    @api.depends("project_id", "product_id", "quantity", "product_uom_id")
    def _compute_order_list_state(self):
        projects = self.project_id.project_id
        product_lines = self.env["tectora.project.order.product"].search([
            ("order_line_id.project_id", "in", projects.ids),
            ("product_id", "in", self.product_id.ids),
        ]) if projects else self.env["tectora.project.order.product"]
        for material in self:
            lines = product_lines.filtered(
                lambda pl: pl.product_id == material.product_id
                and pl.order_line_id.project_id == material.project_id.project_id
            )
            state, covered, details = material._order_list_status(lines)
            material.order_list_state = state
            material.order_list_covered_qty = covered
            material.order_list_info = details

    def _order_list_status(self, lines):
        """(state, quantity covered in this line's unit, detail text) of the
        order list's product lines for this material."""
        self.ensure_one()
        unit = self.product_uom_id or self.product_id.uom_id
        states, covered, details = [], 0.0, []
        for line in lines:
            if line.source == "ordered":
                purchase_line = line.purchase_line_id
                order = purchase_line.order_id
                if order.state in ("draft", "sent", "to approve"):
                    state = "rfq"
                elif purchase_line.uom_id.compare(purchase_line.qty_received, purchase_line.product_qty) >= 0:
                    state = "received"
                else:
                    state = "ordered"
                quantity, uom = line.quantity, line.uom_id
                detail = "%s (%s)" % (order.name, order.partner_id.display_name)
            elif line.source == "stock":
                move = line.move_id
                state = {
                    "done": "stock_done",
                    "assigned": "stock_reserved",
                }.get(move.state, "stock_waiting")
                quantity, uom = move.product_uom_qty, move.uom_id
                detail = move.picking_id.name or ""
            else:
                continue
            if uom and unit and uom != unit and uom._has_common_reference(unit):
                quantity = uom._compute_quantity(quantity, unit, round=False)
            states.append(state)
            covered += quantity
            if detail and detail not in details:
                details.append(detail)
        if states:
            state = min(states, key=STATE_RANK.get)
        elif lines:
            state = "to_order"
        else:
            state = "none"
        if states and unit and unit.compare(covered, self.quantity) < 0:
            details.insert(0, self.env._(
                "deels: %(covered)s van %(needed)s",
                covered=round(covered, 2), needed=round(self.quantity, 2),
            ))
        return state, covered, " · ".join(details)

    def _order_list_covers(self):
        """Whether the order list provides this material already (ordered or
        from the warehouse), whatever is still missing."""
        self.ensure_one()
        return self.order_list_state not in ("none", "to_order")
