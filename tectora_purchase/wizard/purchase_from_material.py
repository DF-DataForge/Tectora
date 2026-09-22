# -*- coding: utf-8 -*-
"""Turn selected material requirement lines into purchase orders.

* A **dropship** order is always one roof project: it carries the site's
  delivery address, the project reference, the planned start of the works
  as the expected arrival, and -- when the same project also has material
  coming through the warehouse -- the flag and the list of what the crew
  picks up at the warehouse on top of the dropship.
* A **warehouse** order is one per vendor, with the lines grouped per roof
  project under a section line that names the project and the site, so the
  vendor sees which delivery belongs to which project.

Lines are priced through Odoo's own vendor pricelist logic
(``purchase.order.line._prepare_purchase_order_line``, the path the
procurement engine uses), and every order line carries the analytic account
of its project, so the purchase lands on the project dashboard.
"""
import logging
from collections import defaultdict

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import format_date

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
        domain="[('delivery_type', 'in', ('dropship', 'warehouse'))]",
        help="Leeg: elke lijn volgt haar eigen route (zoals op het bord "
        "gesleept). Gekozen: alle geselecteerde lijnen gaan via deze route.",
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Leverancier",
        context={"res_partner_search_mode": "supplier"},
        help="Leeg: elke lijn gaat naar haar eigen leverancier. Gekozen: "
        "alles wordt bij deze leverancier besteld.",
    )
    one_order_per_project = fields.Boolean(
        string="Magazijnorders per dakproject splitsen",
        default=False,
        help="Uit: per leverancier één magazijnorder, met de lijnen per "
        "dakproject gegroepeerd. Aan: per leverancier én per dakproject een "
        "aparte order. Een dropship is altijd per werf.",
    )
    date_planned = fields.Datetime(
        string="Gewenste leverdatum",
        help="Leeg: een dropship staat op de geplande start van de werf, een "
        "magazijnlevering volgt de levertermijn van de leverancier.",
    )
    warehouse_pickup = fields.Boolean(
        string="Afhaling aan het magazijn vermelden op de dropship-orders",
        compute="_compute_warehouse_pickup",
        store=True,
        readonly=False,
        help="Op elke dropship-order komt de vlag 'Extra materiaal af te "
        "halen aan het magazijn' met de lijst van het materiaal van dat "
        "dakproject dat aan het magazijn geleverd wordt of uit voorraad "
        "komt.",
    )
    warehouse_pickup_note = fields.Text(
        string="Extra toelichting bij de afhaling",
        help="Wordt onder de lijst van af te halen materiaal gezet.",
    )
    confirm = fields.Boolean(
        string="Inkooporders meteen bevestigen",
        help="Uit: de orders blijven offerteaanvragen die u nakijkt en zelf "
        "bevestigt.",
    )
    line_count = fields.Integer(compute="_compute_summary")
    orderable_count = fields.Integer(compute="_compute_summary")
    skipped_count = fields.Integer(compute="_compute_summary")
    stock_count = fields.Integer(compute="_compute_summary")
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
        if not route or route.delivery_type == "stock":
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

    def _pickup_lines(self, project):
        """What the crew picks up at the warehouse for ``project`` on top of
        a dropship: every line of the project that comes through the
        warehouse or from stock (not only the selected ones)."""
        return project.material_line_ids._lines_via_warehouse()

    @api.depends("material_line_ids", "vendor_id")
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.material_line_ids
            orderable = lines._lines_to_order()
            missing = orderable.filtered(lambda l: not (wizard.vendor_id or l.vendor_id))
            wizard.line_count = len(lines)
            wizard.orderable_count = len(orderable)
            wizard.stock_count = len(lines.filtered(lambda l: l.purchase_state == "stock"))
            wizard.skipped_count = len(lines) - len(orderable) - wizard.stock_count
            wizard.missing_vendor = ", ".join(
                sorted(set(missing.product_id.mapped("display_name")))
            )

    @api.depends("material_line_ids", "logistics_route_id")
    def _compute_warehouse_pickup(self):
        for wizard in self:
            dropship_projects = wizard.material_line_ids.filtered(
                lambda l: wizard._resolve(l)[1].delivery_type == "dropship"
            ).project_id
            wizard.warehouse_pickup = any(
                wizard._pickup_lines(project) for project in dropship_projects
            )

    @api.depends(
        "material_line_ids", "vendor_id", "logistics_route_id",
        "one_order_per_project", "warehouse_pickup",
    )
    def _compute_groups(self):
        Route = self.env["tectora.logistics.route"]
        for wizard in self:
            commands = [Command.clear()]
            for (vendor_id, route_id, project_id, _company_id), lines in sorted(
                wizard._grouped_lines().items(), key=lambda item: item[0]
            ):
                route = Route.browse(route_id)
                amount = sum(line.quantity * line.vendor_price for line in lines)
                pickup_count = 0
                if route.delivery_type == "dropship" and wizard.warehouse_pickup:
                    pickup_count = len(wizard._pickup_lines(lines.project_id[:1]))
                commands.append(
                    Command.create(
                        {
                            "vendor_id": vendor_id,
                            "logistics_route_id": route_id,
                            "project_id": project_id or False,
                            "project_count": len(lines.project_id),
                            "line_count": len(lines),
                            "product_count": len(lines.product_id),
                            "amount_estimate": amount,
                            "pickup_count": pickup_count,
                            "date_planned": (
                                wizard.date_planned
                                or (
                                    lines.project_id[:1].planned_date_begin
                                    if route.delivery_type == "dropship"
                                    else False
                                )
                            ),
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

    # --- order header -----------------------------------------------------------
    def _project_label(self, project):
        """"DP00012 — Kerkstraat 12, 9000 Gent" : how a project is named
        towards the vendor."""
        parts = [project.code if project.code and project.code != _("New") else "", project.name]
        label = " — ".join(filter(None, parts))
        if project.address:
            label = "%s, %s" % (label, project.address)
        return label

    def _pickup_note(self, project):
        """The text of the warehouse pickup on a dropship order: the
        project's material that comes through the warehouse or from stock,
        with its status, plus the wizard's own remark."""
        pickup = self._pickup_lines(project)
        if not pickup and not self.warehouse_pickup_note:
            return False
        state_labels = dict(pickup._fields["purchase_state"].selection)
        route_labels = dict(
            self.env["tectora.logistics.route"]._fields["delivery_type"].selection
        )
        rows = []
        for line in pickup.sorted(lambda l: (l.vendor_id.display_name or "", l.product_id.display_name)):
            rows.append(
                "• %s: %s %s — %s%s (%s)"
                % (
                    line.product_id.display_name,
                    "%g" % line.quantity,
                    line.product_uom_id.name or line.product_id.uom_id.name or "",
                    route_labels.get(line.delivery_type, ""),
                    " bij %s" % line.vendor_id.display_name
                    if line.delivery_type == "warehouse" and line.vendor_id
                    else "",
                    state_labels.get(line.purchase_state, ""),
                )
            )
        text = _(
            "Af te halen aan het magazijn voor %(project)s, naast deze "
            "dropship-levering op de werf:\n%(rows)s",
            project=self._project_label(project),
            rows="\n".join(rows) if rows else _("(nog geen materiaal via het magazijn)"),
        )
        if self.warehouse_pickup_note:
            text = "%s\n\n%s" % (text, self.warehouse_pickup_note)
        return text

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
            label = project.code if project.code and project.code != _("New") else project.name
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
            project = projects[:1]
            destination = project._tectora_delivery_partner()
            if not destination:
                raise UserError(
                    _(
                        "Dakproject %s heeft geen klant of leveradres, dus "
                        "geen bestemming voor een dropship.",
                        project.display_name,
                    )
                )
            values["dest_address_id"] = destination.id
            values["origin"] = self._project_label(project) + (
                " (%s)" % project.sale_order_id.name if project.sale_order_id else ""
            )
            if self.warehouse_pickup:
                note = self._pickup_note(project)
                values["tectora_warehouse_pickup"] = bool(note)
                values["tectora_warehouse_pickup_note"] = note
        return values

    def _line_date_planned(self, route, project):
        """Expected arrival of a line: the wizard's date, else for a dropship
        the planned start of the works (the material must be on site that
        day), else the vendor's lead time (None: leave it to Odoo)."""
        if self.date_planned:
            return self.date_planned
        if route.delivery_type == "dropship" and project.planned_date_begin:
            return project.planned_date_begin
        return None

    # --- order lines ------------------------------------------------------------
    def _analytic_accounts(self, projects):
        """{roof project: analytic account}. The plannable project (and its
        account) is created on the spot when the order was never confirmed;
        a project that cannot be created must not stop the order."""
        accounts = {}
        for project in projects:
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
        return accounts

    def _create_purchase_order(self, vendor, route, company, lines):
        PurchaseOrder = self.env["purchase.order"].with_company(company)
        PurchaseLine = self.env["purchase.order.line"].with_company(company)
        order = PurchaseOrder.create(
            self._purchase_order_values(vendor, route, company, lines)
        )
        accounts = self._analytic_accounts(lines.project_id)

        # One order line per project, product and unit: the same material
        # exploded from two sold works items is ordered once.
        buckets = {}
        for line in lines:
            uom = line.product_uom_id or line.product_id.uom_id
            key = (line.project_id, line.product_id, uom)
            quantity, members = buckets.get(key, (0.0, self.env["tectora.roof.material"]))
            buckets[key] = (quantity + line.quantity, members | line)

        projects = lines.project_id.sorted(lambda p: (p.planned_date_begin or fields.Datetime.now(), p.code or ""))
        with_sections = route.delivery_type != "dropship"
        sequence = 10
        for project in projects:
            if with_sections:
                # The vendor sees which lines belong to which site.
                section = self._project_label(project)
                if project.planned_date_begin:
                    section = "%s — %s %s" % (
                        section,
                        _("start werf"),
                        format_date(
                            self.env,
                            fields.Datetime.context_timestamp(self, project.planned_date_begin),
                        ),
                    )
                PurchaseLine.create(
                    {
                        "order_id": order.id,
                        "display_type": "line_section",
                        "name": section,
                        "sequence": sequence,
                        "product_qty": 0.0,
                    }
                )
                sequence += 1
            date_planned = self._line_date_planned(route, project)
            account = accounts.get(project)
            project_buckets = sorted(
                (item for item in buckets.items() if item[0][0] == project),
                key=lambda item: (item[0][1].display_name or "", item[0][2].id),
            )
            for (_project, product, uom), (quantity, members) in project_buckets:
                values = PurchaseLine._prepare_purchase_order_line(
                    product, quantity, uom, company, vendor, order
                )
                values["sequence"] = sequence
                sequence += 1
                if date_planned:
                    values["date_planned"] = date_planned
                if account:
                    values["analytic_distribution"] = {str(account.id): 100.0}
                order_line = PurchaseLine.create(values)
                # The link is technical bookkeeping: a purchase user without
                # write access on the material list may still order it.
                members.sudo().write({"purchase_line_id": order_line.id})

        self._log_creation(order, vendor, route, lines)
        return order

    def _log_creation(self, order, vendor, route, lines):
        route_label = dict(route._fields["delivery_type"].selection)[route.delivery_type]
        for project in lines.project_id:
            body = _(
                "Inkooporder %(order)s aangemaakt bij %(vendor)s uit de "
                "materiaalbehoefte: %(count)s lijn(en), %(route)s.",
                order=order._get_html_link(),
                vendor=vendor.display_name,
                count=len(lines.filtered(lambda l: l.project_id == project)),
                route=route_label,
            )
            if order.tectora_warehouse_pickup:
                body += Markup(
                    "<br/><b>%s</b><br/><pre class='mb-0'>%s</pre>"
                ) % (
                    _("Extra materiaal af te halen aan het magazijn (zie de dropship-order):"),
                    order.tectora_warehouse_pickup_note or "",
                )
            project.message_post(body=body)
            if order.tectora_warehouse_pickup and project.project_id:
                # The crew reads the plannable project's dashboard.
                project.project_id.message_post(
                    body=Markup("%s<br/><pre class='mb-0'>%s</pre>")
                    % (
                        _(
                            "Dropship-order %(order)s levert op de werf; daarnaast "
                            "extra materiaal af te halen aan het magazijn:",
                            order=order._get_html_link(),
                        ),
                        order.tectora_warehouse_pickup_note or "",
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
    _order = "logistics_route_id, vendor_id, project_id, id"

    wizard_id = fields.Many2one(
        "tectora.purchase.from.material", required=True, ondelete="cascade"
    )
    vendor_id = fields.Many2one("res.partner", string="Leverancier", readonly=True)
    logistics_route_id = fields.Many2one(
        "tectora.logistics.route", string="Logistieke route", readonly=True
    )
    delivery_type = fields.Selection(
        related="logistics_route_id.delivery_type", string="Levering"
    )
    project_id = fields.Many2one(
        "tectora.roof.project", string="Dakproject", readonly=True
    )
    project_count = fields.Integer(string="Dakprojecten", readonly=True)
    line_count = fields.Integer(string="Materiaallijnen", readonly=True)
    product_count = fields.Integer(string="Producten", readonly=True)
    pickup_count = fields.Integer(
        string="Af te halen aan magazijn",
        readonly=True,
        help="Materiaallijnen van het dakproject die de ploeg aan het "
        "magazijn ophaalt; ze worden op de dropship-order vermeld.",
    )
    date_planned = fields.Datetime(string="Verwacht op", readonly=True)
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
