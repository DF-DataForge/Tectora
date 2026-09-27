# -*- coding: utf-8 -*-
"""A material requirement line knows its vendor, its logistic route and the
stock of its product and, once ordered, follows its purchase order line.

The lines are organised on a kanban board with one column per logistic
route: dragging a card to another column changes the route, which is how
the office decides what the vendor ships to the site, what comes to the
warehouse and what is taken from stock.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TectoraRoofMaterial(models.Model):
    _inherit = "tectora.roof.material"

    logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        compute="_compute_logistics_route_id",
        store=True,
        readonly=False,
        index=True,
        group_expand="_read_group_logistics_routes",
        help="Dropship naar de werf, levering aan het magazijn of uit "
        "voorraad. Volgt het product; per lijn aan te passen, ook door de "
        "kaart naar een andere kolom te slepen.",
    )
    delivery_type = fields.Selection(
        related="logistics_route_id.delivery_type", string="Levering"
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
            ("stock", "Uit voorraad"),
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

    # --- stock of the product -------------------------------------------------
    is_storable = fields.Boolean(related="product_id.is_storable")
    qty_available = fields.Float(
        related="product_id.qty_available", string="Voorraad"
    )
    free_qty = fields.Float(
        related="product_id.free_qty",
        string="Vrij beschikbaar",
        help="Voorraad in het magazijn die nog niet voor een andere levering "
        "gereserveerd is (in de eenheid van het product).",
    )
    virtual_available = fields.Float(
        related="product_id.virtual_available", string="Verwacht"
    )
    qty_shortage = fields.Float(
        string="Tekort",
        compute="_compute_stock_state",
        digits="Product Unit of Measure",
        help="Wat er van de behoefte niet uit de vrije voorraad kan komen.",
    )
    stock_state = fields.Selection(
        [
            ("enough", "Volledig op voorraad"),
            ("partial", "Deels op voorraad"),
            ("none", "Niet op voorraad"),
            ("untracked", "Geen voorraadbeheer"),
        ],
        string="Voorraadstatus",
        compute="_compute_stock_state",
        search="_search_stock_state",
    )
    project_planned_date_begin = fields.Datetime(
        related="project_id.planned_date_begin", string="Geplande start"
    )
    purchase_date_planned = fields.Datetime(
        related="purchase_line_id.date_planned", string="Verwacht op"
    )

    # --- the transfer behind the purchase (receipt or dropship) ----------------
    picking_ids = fields.Many2many(
        "stock.picking",
        string="Leveringen",
        compute="_compute_pickings",
        help="De ontvangsten (levering aan magazijn) of dropship-leveringen "
        "die uit de inkooplijn volgen.",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Levering",
        compute="_compute_pickings",
        help="De lopende levering van de inkooplijn, anders de laatste.",
    )
    picking_state = fields.Selection(
        related="picking_id.state", string="Leveringsstatus"
    )

    # ------------------------------------------------------------- computes
    @api.model
    def _read_group_logistics_routes(self, routes, domain):
        return routes._read_group_routes(routes, domain)

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
        # Odoo 20: _select_seller returns the seller's info as a dict, the
        # vendor pricelist line under "supplierinfo".
        seller = product._select_seller(
            partner_id=self.vendor_id if self.vendor_id in product.sudo().seller_ids.partner_id else False,
            quantity=self.quantity or 0.0,
            date=fields.Date.context_today(self),
            uom_id=self.product_uom_id or product.uom_id,
        ).get("supplierinfo")
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
            ).get("supplierinfo") or product._prepare_sellers()[:1]
            line.vendor_id = seller.partner_id

    @api.depends("product_id", "vendor_id", "quantity", "product_uom_id")
    def _compute_vendor_price(self):
        for line in self:
            seller = line._select_seller()
            if seller and seller.partner_id == line.vendor_id:
                uom = line.product_uom_id or line.product_id.uom_id
                seller_uom = seller.uom_id or line.product_id.uom_id
                line.vendor_price = seller_uom._compute_price(seller.price, uom)
            else:
                line.vendor_price = line.product_id.standard_price

    def _quantity_in_product_uom(self):
        self.ensure_one()
        uom = self.product_uom_id
        product_uom = self.product_id.uom_id
        if uom and product_uom and uom != product_uom:
            return uom._compute_quantity(self.quantity, product_uom)
        return self.quantity

    @api.depends("product_id", "quantity", "product_uom_id", "free_qty")
    def _compute_stock_state(self):
        for line in self:
            product = line.product_id
            if not product or not product.is_storable:
                line.stock_state = "untracked"
                line.qty_shortage = 0.0
                continue
            needed = line._quantity_in_product_uom()
            free = product.free_qty
            uom = product.uom_id
            shortage = max(needed - free, 0.0)
            line.qty_shortage = shortage
            if uom.is_zero(needed):
                line.stock_state = "enough"
            elif uom.is_zero(shortage):
                line.stock_state = "enough"
            elif uom.compare(free, 0.0) > 0:
                line.stock_state = "partial"
            else:
                line.stock_state = "none"

    def _search_stock_state(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            raise UserError(_("Deze zoekbewerking wordt niet ondersteund."))
        values = value if isinstance(value, (list, tuple)) else [value]
        lines = self.search([]).filtered(lambda l: l.stock_state in values)
        negate = operator in ("!=", "not in")
        return [("id", "not in" if negate else "in", lines.ids)]

    @api.depends("purchase_line_id.move_ids.state", "purchase_line_id.move_ids.picking_id")
    def _compute_pickings(self):
        for line in self:
            moves = line.purchase_line_id.move_ids.filtered(
                lambda m: m.state != "cancel" and m.picking_id
            )
            pickings = moves.picking_id.sorted("id")
            live = pickings.filtered(lambda p: p.state not in ("done", "cancel"))
            line.picking_ids = pickings
            line.picking_id = (live or pickings)[-1:] if pickings else False

    @api.depends(
        "purchase_line_id",
        "purchase_line_id.state",
        "purchase_line_id.product_qty",
        "purchase_line_id.qty_received",
        "logistics_route_id.delivery_type",
    )
    def _compute_purchase_state(self):
        for line in self:
            po_line = line.purchase_line_id
            if not po_line or po_line.state == "cancel":
                if line.logistics_route_id.delivery_type == "stock":
                    line.purchase_state = "stock"
                else:
                    line.purchase_state = "to_order"
            elif po_line.state in ("purchase", "done"):
                received = (
                    po_line.uom_id.compare(po_line.qty_received, po_line.product_qty) >= 0
                )
                line.purchase_state = "received" if received else "ordered"
            else:
                line.purchase_state = "rfq"

    # -------------------------------------------------------------- ordering
    def _lines_to_order(self):
        """The lines that can go on a purchase order: goods with a quantity
        that are not on a live purchase order yet and are not taken from
        stock. Services (labour exploded from a bill of materials) are never
        ordered."""
        return self.filtered(
            lambda line: line.purchase_state == "to_order"
            and line.product_id
            and line.product_id.type == "consu"
            and line.quantity > 0
        )

    def _lines_via_warehouse(self):
        """The lines the crew takes along from the warehouse: delivered to
        the warehouse or taken from stock (the counterpart of a dropship)."""
        return self.filtered(
            lambda line: line.logistics_route_id.delivery_type in ("warehouse", "stock")
            and line.product_id
            and line.product_id.type == "consu"
            and line.quantity > 0
        )

    def _selected_lines(self):
        """The lines a header button acts on: the selection, else every line
        of the view (the kanban's header button passes ``active_domain``)."""
        if self:
            return self
        domain = self.env.context.get("active_domain")
        if domain:
            return self.search(domain)
        project_id = self.env.context.get("default_project_id")
        if project_id:
            return self.search([("project_id", "=", project_id)])
        return self

    def action_create_purchase_orders(self):
        """Open the wizard that turns the selected lines into purchase orders
        at their vendors (kanban and list header buttons, Actie menu, roof
        project)."""
        lines = self._selected_lines()._lines_to_order()
        if not lines:
            raise UserError(
                _(
                    "Geen te bestellen materiaal geselecteerd: de gekozen "
                    "lijnen zijn al besteld, komen uit voorraad, of het zijn "
                    "geen goederen."
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

    def action_set_route(self):
        """Move the lines to the route given in the context (card menu of the
        kanban, for whoever prefers a click to a drag)."""
        route_id = self.env.context.get("tectora_route_id")
        if route_id:
            self.write({"logistics_route_id": route_id})
        return True

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
