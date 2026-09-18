# -*- coding: utf-8 -*-
"""A material requirement line knows its vendor and its logistic route and,
once ordered, follows its purchase order line."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class TectoraRoofMaterial(models.Model):
    _inherit = "tectora.roof.material"

    logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        compute="_compute_logistics_route_id",
        store=True,
        readonly=False,
        index=True,
        help="Dropship naar de werf of levering aan het magazijn. Volgt het "
        "product; per lijn aan te passen.",
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Leverancier",
        compute="_compute_vendor_id",
        store=True,
        readonly=False,
        index=True,
        context={"res_partner_search_mode": "supplier"},
        help="De leverancier bij wie dit materiaal besteld wordt: de "
        "leverancier uit de inkoopprijslijst van het product; per lijn aan te "
        "passen.",
    )
    vendor_price = fields.Float(
        string="Inkoopprijs",
        compute="_compute_vendor_price",
        digits="Product Price",
        help="Prijs per eenheid uit de inkoopprijslijst van de leverancier "
        "(in de valuta van die prijslijst); zonder prijslijst de kostprijs.",
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="Inkooplijn",
        readonly=True,
        copy=False,
        ondelete="set null",
        index=True,
    )
    purchase_order_id = fields.Many2one(
        related="purchase_line_id.order_id", string="Inkooporder", store=True
    )
    purchase_state = fields.Selection(
        [
            ("to_order", "Te bestellen"),
            ("rfq", "Offerteaanvraag"),
            ("ordered", "Besteld"),
            ("received", "Ontvangen"),
        ],
        string="Inkoopstatus",
        compute="_compute_purchase_state",
        store=True,
    )
    qty_received = fields.Float(
        related="purchase_line_id.qty_received",
        string="Ontvangen",
        help="Ontvangen hoeveelheid van de inkooplijn (in de eenheid van die "
        "lijn).",
    )

    # ------------------------------------------------------------- computes
    @api.depends("product_id")
    def _compute_logistics_route_id(self):
        Route = self.env["tectora.logistics.route"]
        for line in self:
            line.logistics_route_id = Route._get_route_for_product(
                line.product_id, line.company_id or self.env.company
            )

    def _select_seller(self):
        """The vendor pricelist line for this material, at its quantity;
        the product's first vendor when no line covers that quantity."""
        self.ensure_one()
        product = self.product_id
        if not product:
            return self.env["product.supplierinfo"]
        product = product.with_company(self.company_id or self.env.company)
        seller = product._select_seller(
            partner_id=self.vendor_id if self.vendor_id in product.sudo().seller_ids.partner_id else False,
            quantity=self.quantity or 0.0,
            date=fields.Date.context_today(self),
            uom_id=self.product_uom_id or product.uom_id,
        )
        return seller or product._prepare_sellers()[:1]

    @api.depends("product_id")
    def _compute_vendor_id(self):
        for line in self:
            product = line.product_id
            if not product:
                line.vendor_id = False
                continue
            if line.vendor_id and line.vendor_id in product.sudo().seller_ids.partner_id:
                # A vendor picked by hand that still sells the product stays.
                line.vendor_id = line.vendor_id
                continue
            product = product.with_company(line.company_id or self.env.company)
            seller = product._select_seller(
                quantity=line.quantity or 0.0,
                date=fields.Date.context_today(line),
                uom_id=line.product_uom_id or product.uom_id,
            ) or product._prepare_sellers()[:1]
            line.vendor_id = seller.partner_id

    @api.depends("product_id", "vendor_id", "quantity", "product_uom_id")
    def _compute_vendor_price(self):
        for line in self:
            seller = line._select_seller()
            if seller and seller.partner_id == line.vendor_id:
                uom = line.product_uom_id or line.product_id.uom_id
                seller_uom = seller.product_uom_id or line.product_id.uom_id
                line.vendor_price = seller_uom._compute_price(seller.price, uom)
            else:
                line.vendor_price = line.product_id.standard_price

    @api.depends(
        "purchase_line_id",
        "purchase_line_id.state",
        "purchase_line_id.product_qty",
        "purchase_line_id.qty_received",
    )
    def _compute_purchase_state(self):
        for line in self:
            po_line = line.purchase_line_id
            if not po_line or po_line.state == "cancel":
                line.purchase_state = "to_order"
            elif po_line.state in ("purchase", "done"):
                rounding = po_line.product_uom_id.rounding or 0.01
                received = (
                    float_compare(
                        po_line.qty_received, po_line.product_qty,
                        precision_rounding=rounding,
                    )
                    >= 0
                )
                line.purchase_state = "received" if received else "ordered"
            else:
                line.purchase_state = "rfq"

    # -------------------------------------------------------------- ordering
    def _lines_to_order(self):
        """The lines that can go on a purchase order: goods with a quantity
        that are not on a live purchase order yet. Services (labour exploded
        from a bill of materials) are never ordered."""
        return self.filtered(
            lambda line: line.purchase_state == "to_order"
            and line.product_id
            and line.product_id.type == "consu"
            and line.quantity > 0
        )

    def action_create_purchase_orders(self):
        """Open the wizard that turns the selected lines into purchase orders
        at their vendors (list header button, Actie menu, roof project)."""
        lines = self._lines_to_order()
        if not lines:
            raise UserError(
                _(
                    "Geen te bestellen materiaal geselecteerd: de gekozen "
                    "lijnen zijn al besteld, of het zijn geen goederen."
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Inkooporders aanmaken"),
            "res_model": "tectora.purchase.from.material",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_material_line_ids": [(6, 0, lines.ids)],
            },
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": self.purchase_order_id.id,
        }
