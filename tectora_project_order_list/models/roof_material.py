# -*- coding: utf-8 -*-
"""The material list follows the order list: per product, where its order
stands (request for quotation, ordered, received) or its delivery from the
warehouse (waiting, reserved, delivered), computed live from the project's
order list, so it is always up to date.

The material list's own purchase status and purchase order (tectora_purchase)
follow the order list too, unless the material list ordered the product
itself: one truth per product, whichever way it was ordered."""
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


# The purchase states of tectora_purchase, from the least to the most advanced.
PURCHASE_RANK = {"rfq": 0, "ordered": 1, "received": 2}


class TectoraRoofMaterial(models.Model):
    _inherit = "tectora.roof.material"

    order_list_product_ids = fields.Many2many(
        "tectora.project.order.product",
        "tectora_roof_material_order_product_rel",
        "material_id",
        "order_product_id",
        string="Bestellijstproducten",
        compute="_compute_order_list_product_ids",
        store=True,
        help="De producten op de bestellijst van het project voor dit product.",
    )
    purchase_order_id = fields.Many2one(
        "purchase.order",
        related=None,
        compute="_compute_purchase_order_id",
        store=True,
        index=True,
        help="De aankooporder van dit materiaal: die van de materiaallijst "
        "zelf, anders die van de bestellijst.",
    )

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

    @api.depends(
        "product_id",
        "project_id.project_id.tectora_order_line_ids.product_line_ids.product_id",
    )
    def _compute_order_list_product_ids(self):
        for material in self:
            material.order_list_product_ids = (
                material.project_id.project_id.tectora_order_line_ids.product_line_ids.filtered(
                    lambda pl: material.product_id and pl.product_id == material.product_id
                )
            )

    @api.depends("order_list_product_ids", "quantity", "product_uom_id")
    def _compute_order_list_state(self):
        for material in self:
            state, covered, details = material._order_list_status(material.order_list_product_ids)
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

    # ------------------------------------------------- tectora_purchase status
    def _own_purchase_line(self):
        """The material list's own live purchase order line, if any."""
        self.ensure_one()
        line = self.purchase_line_id
        return line if line and line.state != "cancel" else line.browse()

    def _order_list_purchase_lines(self):
        """The live purchase order lines the order list made for this product."""
        self.ensure_one()
        return self.order_list_product_ids.filtered(
            lambda pl: pl.source == "ordered"
        ).purchase_line_id.sorted("id")

    @api.depends("purchase_line_id.order_id", "order_list_product_ids.purchase_line_id.order_id.state")
    def _compute_purchase_order_id(self):
        for material in self:
            material.purchase_order_id = (
                material._own_purchase_line() or material._order_list_purchase_lines()[:1]
            ).order_id

    @api.depends(
        "order_list_product_ids.purchase_line_id.order_id.state",
        "order_list_product_ids.purchase_line_id.product_qty",
        "order_list_product_ids.purchase_line_id.qty_received",
        "order_list_product_ids.move_id.state",
    )
    def _compute_purchase_state(self):
        super()._compute_purchase_state()
        for material in self:
            if material._own_purchase_line():
                continue
            states = []
            for line in material._order_list_purchase_lines():
                if line.order_id.state in ("draft", "sent", "to approve"):
                    states.append("rfq")
                elif line.uom_id.compare(line.qty_received, line.product_qty) >= 0:
                    states.append("received")
                else:
                    states.append("ordered")
            if states:
                # Ordered in two goes: the step that is still behind.
                material.purchase_state = min(states, key=PURCHASE_RANK.get)
            elif any(pl.source == "stock" for pl in material.order_list_product_ids):
                material.purchase_state = "stock"
