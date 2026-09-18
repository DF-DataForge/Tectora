# -*- coding: utf-8 -*-
"""Logistic routes: where purchased material goes.

Two routes ship with the module -- dropship to the site and delivery to the
warehouse -- and the office can add its own (a second warehouse, a dropship
route for one company). A route boils down to the operation type a purchase
order gets, which is what decides, once that order is confirmed, whether Odoo
creates a dropship transfer (vendor -> customer) or a receipt (vendor ->
stock). The matching Odoo stock route is kept on the record so a product's
own routes can be read back to a logistic route.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class TectoraLogisticsRoute(models.Model):
    _name = "tectora.logistics.route"
    _description = "Logistieke route"
    _order = "sequence, id"

    name = fields.Char(string="Naam", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Bedrijf",
        help="Leeg: beschikbaar voor alle bedrijven.",
    )
    delivery_type = fields.Selection(
        [
            ("dropship", "Dropship — rechtstreeks naar de werf"),
            ("warehouse", "Levering aan magazijn"),
        ],
        string="Levering",
        required=True,
        default="warehouse",
        help="Dropship: de leverancier levert op de werf, de inkooporder "
        "krijgt het leveradres van het dakproject. Magazijn: de leverancier "
        "levert aan het magazijn, de inkooporder krijgt de ontvangst van dat "
        "magazijn.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Magazijn",
        compute="_compute_warehouse_id",
        store=True,
        readonly=False,
        help="Het magazijn dat de levering ontvangt (enkel voor levering aan "
        "magazijn).",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operatie op de inkooporder",
        compute="_compute_picking_type_id",
        store=True,
        readonly=False,
        domain="[('code', 'in', ('incoming', 'dropship'))]",
        help="De operatie die de inkooporders van deze route krijgen: de "
        "dropship-operatie of de ontvangst van het magazijn. Wordt afgeleid "
        "uit de levering en kan hier overschreven worden.",
    )
    stock_route_id = fields.Many2one(
        "stock.route",
        string="Odoo-route",
        compute="_compute_stock_route_id",
        store=True,
        readonly=False,
        help="De voorraadroute van Odoo die met deze logistieke route "
        "overeenkomt (Dropship, of de Buy-route van het magazijn). Een "
        "product dat deze route draagt, volgt deze logistieke route.",
    )
    is_default = fields.Boolean(
        string="Standaardroute",
        help="De route voor materiaal zonder eigen route op het product.",
    )
    note = fields.Text(string="Toelichting")
    material_count = fields.Integer(compute="_compute_material_count")

    # ------------------------------------------------------------- computes
    @api.depends("delivery_type", "company_id")
    def _compute_warehouse_id(self):
        Warehouse = self.env["stock.warehouse"]
        for route in self:
            if route.delivery_type != "warehouse":
                route.warehouse_id = False
            elif not route.warehouse_id or (
                route.company_id and route.warehouse_id.company_id != route.company_id
            ):
                company = route.company_id or self.env.company
                route.warehouse_id = Warehouse.search(
                    [("company_id", "=", company.id)], limit=1
                )

    @api.depends("delivery_type", "warehouse_id", "company_id")
    def _compute_picking_type_id(self):
        for route in self:
            route.picking_type_id = route._find_picking_type(
                route.company_id or self.env.company
            )

    @api.depends("delivery_type", "warehouse_id")
    def _compute_stock_route_id(self):
        dropship = self.env.ref(
            "stock_dropshipping.route_drop_shipping", raise_if_not_found=False
        )
        for route in self:
            if route.delivery_type == "dropship":
                route.stock_route_id = dropship
            else:
                route.stock_route_id = route.warehouse_id.buy_pull_id.route_id

    def _compute_material_count(self):
        groups = self.env["tectora.roof.material"]._read_group(
            [("logistics_route_id", "in", self.ids)],
            ["logistics_route_id"],
            ["__count"],
        )
        counts = {route.id: count for route, count in groups}
        for route in self:
            route.material_count = counts.get(route.id, 0)

    @api.constrains("delivery_type", "warehouse_id")
    def _check_warehouse(self):
        for route in self:
            if route.delivery_type == "warehouse" and not route.warehouse_id:
                raise ValidationError(
                    _("Kies het magazijn dat de leveringen van route '%s' ontvangt.")
                    % route.name
                )

    # -------------------------------------------------------------- helpers
    def _find_picking_type(self, company):
        """The operation type this route means for ``company``: the company's
        dropship operation, or the receipt of the route's warehouse."""
        self.ensure_one()
        PickingType = self.env["stock.picking.type"]
        if self.delivery_type == "dropship":
            return PickingType.search(
                [("code", "=", "dropship"), ("company_id", "=", company.id)],
                limit=1,
                order="sequence, id",
            )
        warehouse = self.warehouse_id
        if warehouse and warehouse.company_id == company:
            return warehouse.in_type_id
        return PickingType.search(
            [
                ("code", "=", "incoming"),
                ("warehouse_id.company_id", "=", company.id),
            ],
            limit=1,
            order="sequence, id",
        )

    def _picking_type_for_company(self, company):
        """The operation type to put on a purchase order of ``company``: the
        configured one when it belongs to that company, else the company's
        own equivalent (a route shared across companies)."""
        self.ensure_one()
        picking_type = self.picking_type_id
        if picking_type and picking_type.company_id in (company, self.env["res.company"]):
            return picking_type
        return self._find_picking_type(company)

    @api.model
    def _available_domain(self, company=None):
        company = company or self.env.company
        return [("company_id", "in", [False, company.id])]

    @api.model
    def _get_default_route(self, company=None):
        """The route material follows when nothing says otherwise: the one
        flagged as default, else the warehouse route, else the first."""
        domain = self._available_domain(company)
        return (
            self.search(domain + [("is_default", "=", True)], limit=1)
            or self.search(domain + [("delivery_type", "=", "warehouse")], limit=1)
            or self.search(domain, limit=1)
        )

    @api.model
    def _get_route_for_product(self, product, company=None):
        """The logistic route of a product: the one set on the product, else
        the one whose Odoo route the product (or its category) carries, else
        the default route."""
        if not product:
            return self.browse()
        company = company or self.env.company
        chosen = product.product_tmpl_id.tectora_logistics_route_id
        if chosen and chosen.active and chosen.company_id in (company, self.env["res.company"]):
            return chosen
        product_routes = product.route_ids | product.categ_id.total_route_ids
        if product_routes:
            for route in self.search(
                self._available_domain(company) + [("stock_route_id", "!=", False)]
            ):
                if route.stock_route_id in product_routes:
                    return route
        return self._get_default_route(company)

    def action_view_materials(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "tectora_roof.action_tectora_roof_material"
        )
        action["domain"] = [("logistics_route_id", "=", self.id)]
        action["context"] = {"default_logistics_route_id": self.id}
        return action
