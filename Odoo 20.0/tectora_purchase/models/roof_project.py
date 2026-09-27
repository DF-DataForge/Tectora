# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    material_to_order_count = fields.Integer(
        string="Te bestellen", compute="_compute_material_to_order_count"
    )

    @api.depends(
        "material_line_ids.purchase_state",
        "material_line_ids.product_id",
        "material_line_ids.quantity",
    )
    def _compute_material_to_order_count(self):
        for project in self:
            project.material_to_order_count = len(
                project.material_line_ids._lines_to_order()
            )

    logistics_user_id = fields.Many2one(
        "res.users",
        string="Logistiek verantwoordelijke",
        tracking=True,
        domain="[('share', '=', False)]",
        help="Wie de afhalingen, ontvangsten en dropship-leveringen van dit "
        "dakproject opvolgt; staat op de afgedrukte logistieke lijsten.",
    )
    # The three logistic lists of a project, one per delivery mode.
    stock_material_line_ids = fields.One2many(
        "tectora.roof.material",
        "project_id",
        string="Uit eigen magazijn",
        domain=[("logistics_route_id.delivery_type", "=", "stock")],
    )
    warehouse_material_line_ids = fields.One2many(
        "tectora.roof.material",
        "project_id",
        string="Ontvangsten aan magazijn",
        domain=[("logistics_route_id.delivery_type", "=", "warehouse")],
    )
    dropship_material_line_ids = fields.One2many(
        "tectora.roof.material",
        "project_id",
        string="Dropship op de werf",
        domain=[("logistics_route_id.delivery_type", "=", "dropship")],
    )
    stock_material_count = fields.Integer(compute="_compute_logistics_list_counts")
    warehouse_material_count = fields.Integer(compute="_compute_logistics_list_counts")
    dropship_material_count = fields.Integer(compute="_compute_logistics_list_counts")

    dropship_pickup_order_ids = fields.Many2many(
        "purchase.order",
        string="Dropship-orders met afhaling",
        compute="_compute_dropship_pickup_info",
    )
    dropship_pickup_info = fields.Text(
        string="Af te halen aan het magazijn",
        compute="_compute_dropship_pickup_info",
        help="Wat de ploeg aan het magazijn ophaalt naast de dropship-"
        "leveringen op de werf, zoals vermeld op die inkooporders.",
    )

    @api.depends("material_line_ids.logistics_route_id.delivery_type")
    def _compute_logistics_list_counts(self):
        for project in self:
            by_type = {"stock": 0, "warehouse": 0, "dropship": 0}
            for line in project.material_line_ids:
                kind = line.logistics_route_id.delivery_type
                if kind in by_type:
                    by_type[kind] += 1
            project.stock_material_count = by_type["stock"]
            project.warehouse_material_count = by_type["warehouse"]
            project.dropship_material_count = by_type["dropship"]

    # --------------------------------------------------------- logistic lists
    LOGISTICS_LISTS = (
        (
            "stock",
            "Afhaallijst eigen magazijn",
            "Materiaal uit voorraad dat de ploeg aan het magazijn meeneemt; "
            "er wordt niets voor besteld.",
            "deployed_code",
        ),
        (
            "warehouse",
            "Ontvangsten aan het magazijn",
            "Projectspecifieke bestellingen die de leverancier aan het "
            "magazijn levert; de ploeg neemt ze van daar mee.",
            "local_shipping",
        ),
        (
            "dropship",
            "Rechtstreeks op de werf geleverd (dropship)",
            "Bestellingen die de leverancier rechtstreeks op de werf levert, "
            "tegen de geplande start van de werken.",
            "location_on",
        ),
    )

    def _logistics_pickings(self, kind, lines):
        """The transfers behind a list: the material transfers of the stock
        bridge for the stock list, the receipts or dropships of the purchase
        lines for the two others."""
        self.ensure_one()
        Picking = self.env["stock.picking"]
        if kind == "stock":
            if "material_picking_ids" in self._fields:  # tectora_roof_stock
                return self.material_picking_ids.filtered(lambda p: p.state != "cancel")
            return Picking
        moves = lines.purchase_line_id.move_ids.filtered(
            lambda m: m.state != "cancel" and m.picking_id
        )
        return moves.picking_id.sorted("scheduled_date, id")

    def _logistics_lists(self, keys=None):
        """The three logistic lists of the project, for the print and the
        portal: [{key, title, subtitle, icon, lines, pickings, orders,
        pickup_orders}], lines sorted per vendor and product."""
        self.ensure_one()
        lists = []
        for key, title, subtitle, icon in self.LOGISTICS_LISTS:
            if keys and key not in keys:
                continue
            lines = self.material_line_ids.filtered(
                lambda l, key=key: l.logistics_route_id.delivery_type == key
                and l.product_id
                and l.product_id.type == "consu"
            ).sorted(
                lambda l: (l.vendor_id.display_name or "", l.product_id.display_name or "")
            )
            orders = lines.purchase_order_id.filtered(lambda o: o.state != "cancel")
            lists.append(
                {
                    "key": key,
                    "title": title,
                    "subtitle": subtitle,
                    "icon": icon,
                    "lines": lines,
                    "pickings": self._logistics_pickings(key, lines),
                    "orders": orders.sorted("name"),
                    "pickup_orders": orders.filtered("tectora_warehouse_pickup")
                    if key == "dropship"
                    else orders.browse(),
                }
            )
        return lists

    def action_print_logistics_lists(self):
        return self.env.ref(
            "tectora_purchase.action_report_logistics_lists"
        ).report_action(self)

    def _tectora_delivery_partner(self):
        """Where a dropship for this project goes: the delivery address of the
        order, else the customer."""
        self.ensure_one()
        order = self.sale_order_id
        partner = order.partner_shipping_id if order else self.env["res.partner"]
        return partner or self.partner_id

    def _get_purchase_orders(self):
        """Purchase orders of the project: the ones carrying its analytic
        account (as before) and the ones created from its material list, so
        the Inkoop button is right even before the project has an analytic
        account."""
        orders = super()._get_purchase_orders()
        linked = self.env["purchase.order"].search(
            [("tectora_roof_project_id", "=", self.id)]
        )
        if orders is None:
            return linked
        return orders | linked

    def action_create_purchase_orders(self):
        """Order the material of this roof project that is not ordered yet."""
        self.ensure_one()
        return self.material_line_ids.action_create_purchase_orders()

    def action_organize_purchases(self):
        """The ordering board of this project: one column per logistic
        route, cards dragged from one to the other, vendors and stock on
        every card, and the purchase orders made from there."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "tectora_purchase.action_tectora_material_organize"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["display_name"] = _("Inkoop organiseren — %s", self.display_name)
        action["context"] = {
            "default_project_id": self.id,
            "search_default_open": 1,
        }
        return action

    @api.depends(
        "material_line_ids.purchase_order_id.tectora_warehouse_pickup",
        "material_line_ids.purchase_order_id.state",
    )
    def _compute_dropship_pickup_info(self):
        for project in self:
            orders = project.material_line_ids.purchase_order_id.filtered(
                lambda o: o.tectora_warehouse_pickup and o.state != "cancel"
            )
            orders |= self.env["purchase.order"].search(
                [
                    ("tectora_roof_project_id", "=", project.id),
                    ("tectora_warehouse_pickup", "=", True),
                    ("state", "!=", "cancel"),
                ]
            )
            project.dropship_pickup_order_ids = orders
            project.dropship_pickup_info = "\n\n".join(
                "%s: %s" % (order.name, order.tectora_warehouse_pickup_note or "")
                for order in orders
            )
