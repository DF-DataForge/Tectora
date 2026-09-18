# -*- coding: utf-8 -*-
"""Turn selected material requirement lines into purchase orders.

One purchase order per vendor, per logistic route and per roof project. A
dropship order is always per project, since it carries the site's delivery
address; warehouse deliveries of several projects can be merged onto one
order. Lines are priced through Odoo's own vendor pricelist logic
(``purchase.order.line._prepare_purchase_order_line``, the path the
procurement engine uses), and every order line carries the analytic account
of the project, so the purchase lands on the project dashboard.
"""
import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TectoraPurchaseFromMaterial(models.TransientModel):
    _name = "tectora.purchase.from.material"
    _description = "Inkooporders aanmaken uit materiaalbehoefte"

    material_line_ids = fields.Many2many(
        "tectora.roof.material",
        "tectora_purchase_wizard_material_rel",
        "wizard_id",
        "material_id",
        string="Materiaallijnen",
    )
    logistics_route_id = fields.Many2one(
        "tectora.logistics.route",
        string="Logistieke route",
        help="Leeg: elke lijn volgt haar eigen route. Gekozen: alle "
        "geselecteerde lijnen gaan via deze route.",
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Leverancier",
        context={"res_partner_search_mode": "supplier"},
        help="Leeg: elke lijn gaat naar haar eigen leverancier. Gekozen: "
        "alles wordt bij deze leverancier besteld.",
    )
    one_order_per_project = fields.Boolean(
        string="Eén inkooporder per dakproject",
        default=True,
        help="Uit: lijnen van verschillende dakprojecten voor dezelfde "
        "leverancier komen op één inkooporder (enkel bij levering aan het "
        "magazijn; een dropship is altijd per werf).",
    )
    date_planned = fields.Datetime(
        string="Gewenste leverdatum",
        help="Leeg: de levertermijn van de leverancier.",
    )
    confirm = fields.Boolean(
        string="Inkooporders meteen bevestigen",
        help="Uit: de orders blijven offerteaanvragen die u nakijkt en zelf "
        "bevestigt.",
    )
    line_count = fields.Integer(compute="_compute_summary")
    orderable_count = fields.Integer(compute="_compute_summary")
    skipped_count = fields.Integer(compute="_compute_summary")
    missing_vendor = fields.Char(compute="_compute_summary")
    group_ids = fields.One2many(
        "tectora.purchase.from.material.group",
        "wizard_id",
        string="Inkooporders",
        compute="_compute_groups",
    )

    # -------------------------------------------------------------- resolve
    def _resolve(self, line):
        """(vendor, route) of a material line, with the wizard's overrides."""
        vendor = self.vendor_id or line.vendor_id
        route = self.logistics_route_id or line.logistics_route_id
        if not route:
            route = self.env["tectora.logistics.route"]._get_default_route(
                line.company_id or self.env.company
            )
        return vendor, route

    def _group_key(self, line, vendor, route):
        per_project = self.one_order_per_project or route.delivery_type == "dropship"
        return (
            vendor.id,
            route.id,
            line.project_id.id if per_project else 0,
            (line.company_id or self.env.company).id,
        )

    def _grouped_lines(self):
        """{(vendor id, route id, project id or 0, company id): lines}."""
        self.ensure_one()
        groups = defaultdict(lambda: self.env["tectora.roof.material"])
        for line in self.material_line_ids._lines_to_order():
            vendor, route = self._resolve(line)
            if not vendor or not route:
                continue
            groups[self._group_key(line, vendor, route)] |= line
        return groups

    @api.depends("material_line_ids", "vendor_id")
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.material_line_ids
            orderable = lines._lines_to_order()
            missing = orderable.filtered(lambda l: not (wizard.vendor_id or l.vendor_id))
            wizard.line_count = len(lines)
            wizard.orderable_count = len(orderable)
            wizard.skipped_count = len(lines) - len(orderable)
            wizard.missing_vendor = ", ".join(
                sorted(set(missing.product_id.mapped("display_name")))
            )

    @api.depends(
        "material_line_ids", "vendor_id", "logistics_route_id", "one_order_per_project"
    )
    def _compute_groups(self):
        for wizard in self:
            commands = [Command.clear()]
            for (vendor_id, route_id, project_id, _company_id), lines in sorted(
                wizard._grouped_lines().items(), key=lambda item: item[0]
            ):
                amount = sum(line.quantity * line.vendor_price for line in lines)
                commands.append(
                    Command.create(
                        {
                            "vendor_id": vendor_id,
                            "logistics_route_id": route_id,
                            "project_id": project_id or False,
                            "line_count": len(lines),
                            "product_count": len(lines.product_id),
                            "amount_estimate": amount,
                        }
                    )
                )
            wizard.group_ids = commands

    # --------------------------------------------------------------- create
    def action_create_purchase_orders(self):
        self.ensure_one()
        lines = self.material_line_ids._lines_to_order()
        if not lines:
            raise UserError(
                _("Er is geen te bestellen materiaal meer in de selectie.")
            )
        missing = lines.filtered(lambda l: not (self.vendor_id or l.vendor_id))
        if missing:
            raise UserError(
                _(
                    "Geen leverancier voor: %(products)s.\n\nStel een "
                    "leverancier in op de materiaallijn, of zet een "
                    "leverancier op het product (tab Inkoop), of kies "
                    "hieronder één leverancier voor de hele selectie.",
                    products=", ".join(
                        sorted(set(missing.product_id.mapped("display_name")))
                    ),
                )
            )
        groups = self._grouped_lines()
        if not groups:
            raise UserError(
                _(
                    "Geen logistieke route gevonden. Maak er een aan onder "
                    "Dakmeting -> Logistieke routes."
                )
            )
        orders = self.env["purchase.order"]
        for (vendor_id, route_id, _project_id, company_id), group_lines in groups.items():
            orders |= self._create_purchase_order(
                self.env["res.partner"].browse(vendor_id),
                self.env["tectora.logistics.route"].browse(route_id),
                self.env["res.company"].browse(company_id),
                group_lines,
            )
        if self.confirm:
            orders.button_confirm()
        return self._action_open(orders)

    def _purchase_order_values(self, vendor, route, company, lines):
        projects = lines.project_id
        picking_type = route._picking_type_for_company(company)
        if not picking_type:
            raise UserError(
                _(
                    "Geen operatie gevonden voor route '%(route)s' in bedrijf "
                    "%(company)s: controleer de route onder Dakmeting -> "
                    "Logistieke routes.",
                    route=route.name,
                    company=company.name,
                )
            )
        origins = []
        for project in projects:
            label = project.code or project.name
            if project.sale_order_id:
                label = "%s / %s" % (label, project.sale_order_id.name)
            origins.append(label)
        values = {
            "partner_id": vendor.id,
            "company_id": company.id,
            "picking_type_id": picking_type.id,
            "origin": ", ".join(origins),
            "user_id": self.env.user.id,
            "tectora_roof_project_id": projects.id if len(projects) == 1 else False,
            "tectora_logistics_route_id": route.id,
        }
        if route.delivery_type == "dropship":
            # Always one project here (see _group_key).
            destination = projects[:1]._tectora_delivery_partner()
            if not destination:
                raise UserError(
                    _(
                        "Dakproject %s heeft geen klant of leveradres, dus "
                        "geen bestemming voor een dropship.",
                        projects[:1].display_name,
                    )
                )
            values["dest_address_id"] = destination.id
        return values

    def _create_purchase_order(self, vendor, route, company, lines):
        PurchaseOrder = self.env["purchase.order"].with_company(company)
        PurchaseLine = self.env["purchase.order.line"].with_company(company)
        order = PurchaseOrder.create(
            self._purchase_order_values(vendor, route, company, lines)
        )

        # The project's analytic account, so the purchase lands on the project
        # dashboard; created on the spot when the order was never confirmed
        # (material added by hand on a quoted project). A project that cannot
        # be created must not stop the order: it then simply has no analytic
        # account.
        accounts = {}
        for project in lines.project_id:
            account = project.project_id.account_id
            if not account:
                try:
                    with self.env.cr.savepoint():
                        account = project.sudo()._ensure_project().account_id
                except Exception:  # noqa: BLE001 - logged, never blocking
                    _logger.exception(
                        "Could not create the project of roof project %s",
                        project.display_name,
                    )
                    account = False
            accounts[project] = account

        # One order line per project, product and unit: the same material
        # exploded from two sold works items is ordered once.
        buckets = {}
        for line in lines:
            uom = line.product_uom_id or line.product_id.uom_id
            key = (line.project_id, line.product_id, uom)
            quantity, members = buckets.get(key, (0.0, self.env["tectora.roof.material"]))
            buckets[key] = (quantity + line.quantity, members | line)

        for (project, product, uom), (quantity, members) in buckets.items():
            values = PurchaseLine._prepare_purchase_order_line(
                product, quantity, uom, company, vendor, order
            )
            if self.date_planned:
                values["date_planned"] = self.date_planned
            account = accounts.get(project)
            if account:
                values["analytic_distribution"] = {str(account.id): 100.0}
            order_line = PurchaseLine.create(values)
            # The link is technical bookkeeping: a purchase user without
            # write access on the material list may still order it.
            members.sudo().write({"purchase_line_id": order_line.id})

        route_label = dict(route._fields["delivery_type"].selection)[route.delivery_type]
        for project in lines.project_id:
            project.message_post(
                body=_(
                    "Inkooporder %(order)s aangemaakt bij %(vendor)s uit de "
                    "materiaalbehoefte: %(count)s lijn(en), %(route)s.",
                    order=order._get_html_link(),
                    vendor=vendor.display_name,
                    count=len(lines.filtered(lambda l: l.project_id == project)),
                    route=route_label,
                )
            )
        order.message_post(
            body=_(
                "Aangemaakt uit de materiaalbehoefte van %(projects)s "
                "(%(route)s).",
                projects=", ".join(p._get_html_link() for p in lines.project_id),
                route=route.name,
            )
        )
        return order

    def _action_open(self, orders):
        action = {
            "type": "ir.actions.act_window",
            "name": _("Inkooporders"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
            "context": {"create": False},
        }
        if len(orders) == 1:
            action.update({"view_mode": "form", "res_id": orders.id})
        return action


class TectoraPurchaseFromMaterialGroup(models.TransientModel):
    """Preview of one purchase order the wizard is about to create."""

    _name = "tectora.purchase.from.material.group"
    _description = "Inkooporder in voorbereiding"
    _order = "vendor_id, project_id, id"

    wizard_id = fields.Many2one(
        "tectora.purchase.from.material", required=True, ondelete="cascade"
    )
    vendor_id = fields.Many2one("res.partner", string="Leverancier", readonly=True)
    logistics_route_id = fields.Many2one(
        "tectora.logistics.route", string="Logistieke route", readonly=True
    )
    project_id = fields.Many2one(
        "tectora.roof.project", string="Dakproject", readonly=True
    )
    line_count = fields.Integer(string="Materiaallijnen", readonly=True)
    product_count = fields.Integer(string="Producten", readonly=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    amount_estimate = fields.Monetary(
        string="Geschat bedrag",
        currency_field="currency_id",
        readonly=True,
        help="Hoeveelheid x inkoopprijs van de leverancier (kostprijs zonder "
        "prijslijst); de order zelf rekent met de prijslijst van Odoo.",
    )
