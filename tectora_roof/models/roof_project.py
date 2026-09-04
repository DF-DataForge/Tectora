# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
import math
import re

import requests
from PIL import Image, ImageDraw, ImageFont

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_STATIC_URL = "https://maps.googleapis.com/maps/api/staticmap"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places/%s.json"
MAPBOX_STATIC_URL = (
    "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
    "%(lng).7f,%(lat).7f,%(zoom)d/%(w)dx%(h)d@2x"
)

# Web-mercator ground resolution at zoom 0 on the equator (meters per pixel).
EARTH_M_PER_PX = 156543.03392
METERS_PER_DEG_LAT = 111320.0
SATELLITE_ZOOM = 20
REQUEST_TIMEOUT = 25

# 50 px per meter — same default as the legacy standalone canvas when no
# satellite background (and thus no geographic scale) is available.
DEFAULT_SCALE_M_PER_PX = 0.02


def _polygon_area_px(points):
    """Shoelace formula, in squared canvas pixels."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _polygon_perimeter_px(points):
    n = len(points)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def _bounding_box_px(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _point_in_polygon(point, points):
    px, py = point
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i]
        xj, yj = points[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _line_intersection(point1, dir1, point2, dir2):
    cross = dir1[0] * dir2[1] - dir1[1] * dir2[0]
    if abs(cross) < 1e-9:
        return None
    t = ((point2[0] - point1[0]) * dir2[1] - (point2[1] - point1[1]) * dir2[0]) / cross
    return (point1[0] + dir1[0] * t, point1[1] + dir1[1] * t)


def _inset_polygon_px(points, widths):
    """Variable inset (mirror of the canvas widget): each edge moves inward
    by its own width (px); returns None when the result degenerates."""
    n = len(points)
    if n < 3:
        return None
    offset_edges = []
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        probe = ((ax + bx) / 2 + nx * 0.5, (ay + by) / 2 + ny * 0.5)
        if not _point_in_polygon(probe, points):
            nx, ny = -nx, -ny
        width = widths[i] if i < len(widths) else 0.0
        offset_edges.append(((ax + nx * width, ay + ny * width), (dx, dy)))
    inner = []
    for i in range(n):
        previous = offset_edges[i - 1]
        current = offset_edges[i]
        vertex = _line_intersection(previous[0], previous[1], current[0], current[1])
        inner.append(vertex or current[0])

    def signed_area(polygon):
        total = 0.0
        for i in range(len(polygon)):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % len(polygon)]
            total += x1 * y2 - x2 * y1
        return total / 2.0

    # Degenerate widths flip the polygon inside-out: the orientation of the
    # result must match the original.
    signed_inner = signed_area(inner)
    signed_outer = signed_area(points)
    if (
        not signed_inner
        or (signed_inner > 0) != (signed_outer > 0)
        or abs(signed_inner) > abs(signed_outer)
    ):
        return None
    return inner


class TectoraRoofProject(models.Model):
    _name = "tectora.roof.project"
    _description = "Roof Measurement Project"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_names_search = ["name", "code", "partner_id.name"]

    name = fields.Char(string="Projectnaam", required=True, tracking=True)
    code = fields.Char(
        string="Referentie", readonly=True, copy=False, default=lambda self: _("New")
    )
    partner_id = fields.Many2one(
        "res.partner", string="Klant", tracking=True, check_company=True
    )
    opportunity_id = fields.Many2one("crm.lead", string="Opportuniteit")
    address = fields.Char(
        string="Werfadres", compute="_compute_address", store=True, readonly=False
    )
    description = fields.Text(string="Notities")
    state = fields.Selection(
        [
            ("draft", "Concept"),
            ("measured", "Opgemeten"),
            ("quoted", "Offerte gemaakt"),
            ("confirmed", "Order bevestigd"),
            ("done", "Afgerond"),
        ],
        default="draft",
        tracking=True,
    )
    project_type = fields.Selection(
        [
            ("renovatie", "Renovatie"),
            ("nieuwbouw", "Nieuwbouw"),
            ("industrie", "Industrie"),
        ],
        string="Projecttype",
        default="renovatie",
        tracking=True,
        help="Bepaalt de prijslijst op de gegenereerde offerte: er wordt "
        "gezocht naar een prijslijst met dezelfde naam als het projecttype.",
    )
    company_id = fields.Many2one(
        "res.company", string="Bedrijf", default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    # --- Satellite background -------------------------------------------------
    background_image = fields.Image(string="Satellietbeeld", max_width=2560, max_height=2560)
    has_background_image = fields.Boolean(compute="_compute_has_background_image")
    bg_lat = fields.Float(string="Breedtegraad", digits=(16, 7))
    bg_lng = fields.Float(string="Lengtegraad", digits=(16, 7))
    bg_north = fields.Float(digits=(16, 7))
    bg_south = fields.Float(digits=(16, 7))
    bg_east = fields.Float(digits=(16, 7))
    bg_west = fields.Float(digits=(16, 7))
    scale_m_per_px = fields.Float(
        string="Schaal (m per pixel)",
        digits=(16, 6),
        default=DEFAULT_SCALE_M_PER_PX,
        tracking=True,
        help="Geographic scale of the drawing: how many meters one canvas pixel "
        "represents. Set automatically when a satellite image is fetched; can be "
        "corrected manually when working from an uploaded plan, or calibrated "
        "from the drawing by right-clicking a side's length label and entering "
        "the measured length. Calibrating moves nothing, so the drawing keeps "
        "lining up with the background image, but it does make the geographic "
        "bounds (bg_north/south/east/west) of the fetched image approximate.",
    )

    # --- Drawing --------------------------------------------------------------
    canvas_data = fields.Text(
        string="Tekening (JSON)",
        default='{"shapes": []}',
        help="Shapes drawn on the canvas, in image-pixel coordinates.",
    )
    canvas_snapshot = fields.Binary(
        string="Tekening (snapshot)",
        attachment=True,
        help="PNG snapshot of the drawing, stored by the canvas widget on "
        "every change and used on the measurement sheet PDF.",
    )
    canvas_icons = fields.Text(
        string="Iconen op de tekening (JSON)",
        compute="_compute_canvas_icons",
        help="Canvas-id van elk dakobject met de productcategorie waarvan het "
        "icoon getoond wordt. De tekening leest dit; het staat hier omdat de "
        "vormen in canvas_data zelf geen producten kennen.",
    )

    section_ids = fields.One2many(
        "tectora.roof.section", "project_id", string="Daksecties"
    )
    direct_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Projectlijnen",
    )
    general_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Algemene werken",
        domain=[("product_id.categ_id.complete_name", "ilike", "algemene werken")],
    )
    safety_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Veiligheid",
        domain=[("product_id.categ_id.complete_name", "ilike", "veiligheid")],
    )
    demolition_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Afbraak",
        domain=[("product_id.categ_id.complete_name", "ilike", "afbraak")],
    )
    buildup_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Opbouw",
        domain=[("product_id.categ_id.complete_name", "ilike", "opbouw")],
    )
    other_line_ids = fields.One2many(
        "tectora.roof.section.product", "project_direct_id",
        string="Overige projectlijnen",
        domain=[
            ("product_id.categ_id.complete_name", "not ilike", "algemene werken"),
            ("product_id.categ_id.complete_name", "not ilike", "veiligheid"),
            ("product_id.categ_id.complete_name", "not ilike", "afbraak"),
            ("product_id.categ_id.complete_name", "not ilike", "opbouw"),
        ],
        help="Lijnen van de offerte buiten de vier hoofdstukken (dakranden, "
        "regenwaterafvoer, opties...), gespiegeld op het dakproject.",
    )
    roof_object_ids = fields.One2many(
        "tectora.roof.object", "project_id", string="Dakobjecten"
    )
    sale_order_ids = fields.One2many(
        "sale.order", "roof_project_id", string="Offertes / Orders",
        help="Alle offertes en orders die ooit aan dit dakproject hingen; "
        "de actieve staat in Offerte / Order.",
    )
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Offerte / Order",
        compute="_compute_sale_order_id",
        inverse="_inverse_sale_order_id",
        store=True,
        readonly=False,
        copy=False,
        index=True,
        help="De verkooporder van dit dakproject: één dakproject staat "
        "tegenover één offerte/order. Klant, opportuniteit, verkoper, "
        "leverdatum en prijslijst/projecttype worden in beide richtingen "
        "gelijk gehouden. Een geannuleerde order blijft in de historiek "
        "(Offertes / Orders) en maakt plaats voor een nieuwe.",
    )
    sale_order_state = fields.Selection(
        related="sale_order_id.state", string="Orderstatus", readonly=True
    )

    # --- Project dossier: analytic accounting, costs, deliveries, invoices ---
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        copy=False,
        ondelete="set null",
        index=True,
        help="Planbaar Odoo-project achter dit dakproject, aangemaakt bij het "
        "bevestigen van de order. Het draagt de analytische rekening waarop "
        "omzet en kosten (order, facturen, inkoop, leveringen, urenstaten) "
        "samenkomen en toont het projectdashboard.",
    )
    analytic_account_id = fields.Many2one(
        related="project_id.account_id", string="Analytische rekening", readonly=True
    )
    material_line_ids = fields.One2many(
        "tectora.roof.material", "project_id", string="Materiaallijst"
    )
    material_count = fields.Integer(compute="_compute_material_totals")
    material_cost = fields.Monetary(
        string="Materiaalkost",
        compute="_compute_material_totals",
        currency_field="currency_id",
    )
    revenue = fields.Monetary(
        string="Omzet (excl. btw)",
        compute="_compute_revenue",
        currency_field="currency_id",
        help="Bevestigde verkooporders van dit dakproject.",
    )
    margin = fields.Monetary(
        string="Marge",
        compute="_compute_revenue",
        currency_field="currency_id",
        help="Omzet minus de kostprijs van de materiaallijst.",
    )
    picking_count = fields.Integer(compute="_compute_logistics_counts")
    purchase_count = fields.Integer(compute="_compute_logistics_counts")
    invoice_count = fields.Integer(compute="_compute_logistics_counts")

    # --- Planning on teams ---------------------------------------------------
    team_id = fields.Many2one(
        "tectora.roof.team",
        string="Ploeg",
        tracking=True,
        help="Ploeg die de werf uitvoert. Samen met de geplande data wordt "
        "automatisch een werkblok aangemaakt met planning-items voor elke "
        "medewerker van de ploeg.",
    )
    planned_date_begin = fields.Datetime(string="Geplande start", tracking=True)
    planned_date_end = fields.Datetime(string="Gepland einde", tracking=True)
    planning_ids = fields.One2many(
        "tectora.roof.planning", "project_id", string="Werkblokken"
    )
    planning_count = fields.Integer(compute="_compute_planning_count")
    section_count = fields.Integer(
        string="Aantal daksecties", compute="_compute_shape_counts"
    )
    roof_object_count = fields.Integer(
        string="Aantal dakobjecten", compute="_compute_shape_counts"
    )

    total_area = fields.Float(
        string="Totale oppervlakte (m²)",
        compute="_compute_totals",
        store=True,
        digits=(16, 2),
    )
    total_perimeter = fields.Float(
        string="Totale omtrek (m)",
        compute="_compute_totals",
        store=True,
        digits=(16, 2),
    )
    estimated_total = fields.Monetary(
        string="Geschat totaal (excl. btw)",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )

    # ------------------------------------------------------------------ compute
    @api.depends("partner_id")
    def _compute_address(self):
        for project in self:
            if not project.address and project.partner_id:
                project.address = project.partner_id._display_address(
                    without_company=True
                ).replace("\n", ", ")

    def _compute_has_background_image(self):
        for project in self:
            project.has_background_image = bool(project.background_image)

    @api.depends(
        "roof_object_ids.canvas_ref",
        "roof_object_ids.product_line_ids.product_id",
    )
    def _compute_canvas_icons(self):
        """Which category's icon each dakobject shows on the drawing.

        The shapes in canvas_data know nothing about products, so the link runs
        the other way: a dakobject's assigned products name a category, and a
        category that can be used for dakobjecten may carry an icon. The first
        assigned product that has one wins, in line order.
        """
        for project in self:
            icons = {}
            for roof_object in project.roof_object_ids:
                if not roof_object.canvas_ref:
                    continue
                for line in roof_object.product_line_ids:
                    category = line.product_id.categ_id
                    if category.tectora_allows_objects and category.tectora_canvas_icon:
                        icons[roof_object.canvas_ref] = category.id
                        break
            project.canvas_icons = json.dumps(icons)

    def _compute_sale_order_count(self):
        for project in self:
            project.sale_order_count = len(project.sale_order_ids)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for project in self:
            code = project.code if project.code and project.code != _("New") else ""
            project.display_name = " — ".join(filter(None, [code, project.name]))

    @api.depends("sale_order_ids", "sale_order_ids.state")
    def _compute_sale_order_id(self):
        """The one order that stands against this roof project: the most
        recent one that is not cancelled, or -- when every order was
        cancelled -- the most recent one, so the history stays reachable."""
        for project in self:
            orders = project.sale_order_ids.sorted("id", reverse=True)
            current = project.sale_order_id
            if current and current in orders and current.state != "cancel":
                continue
            active = orders.filtered(lambda order: order.state != "cancel")
            project.sale_order_id = (active or orders)[:1]

    def _inverse_sale_order_id(self):
        """Linking an order from the roof project side: the order points back
        at this roof project and any other open order of the project is let
        go, so the pair stays one-to-one. Cancelled orders stay as history."""
        for project in self:
            order = project.sale_order_id
            others = project.sale_order_ids.filtered(
                lambda o: o != order and o.state != "cancel"
            )
            if others:
                others.with_context(tectora_sync=True).write(
                    {"roof_project_id": False}
                )
            if order and order.roof_project_id != project:
                order.with_context(tectora_sync=True).write(
                    {"roof_project_id": project.id}
                )
                order._tectora_sync_pair(project, master="roof")

    @api.depends("planning_ids")
    def _compute_planning_count(self):
        for project in self:
            project.planning_count = len(project.planning_ids)

    @api.depends("material_line_ids.cost_subtotal")
    def _compute_material_totals(self):
        for project in self:
            project.material_count = len(project.material_line_ids)
            project.material_cost = sum(
                project.material_line_ids.mapped("cost_subtotal")
            )

    @api.depends(
        "sale_order_ids.state",
        "sale_order_ids.amount_untaxed",
        "material_line_ids.cost_subtotal",
    )
    def _compute_revenue(self):
        for project in self:
            confirmed = project.sale_order_ids.filtered(
                lambda order: order.state == "sale"
            )
            project.revenue = sum(confirmed.mapped("amount_untaxed"))
            project.margin = project.revenue - sum(
                project.material_line_ids.mapped("cost_subtotal")
            )

    def _compute_logistics_counts(self):
        for project in self:
            orders = project.sale_order_ids
            project.picking_count = len(project._get_pickings())
            project.invoice_count = len(orders.mapped("invoice_ids"))
            purchases = project._get_purchase_orders()
            project.purchase_count = len(purchases) if purchases is not None else 0

    # --------------------------------------------------------- project dossier
    def _get_pickings(self):
        """Deliveries of the project's sale orders (sale_stock)."""
        self.ensure_one()
        orders = self.sale_order_ids
        if not orders or "picking_ids" not in orders._fields:
            return self.env["stock.picking"]
        return orders.mapped("picking_ids")

    def _get_purchase_orders(self):
        """Purchase orders whose lines carry the project's analytic account.

        Returns None when Purchase is not installed (an optional dependency).
        """
        self.ensure_one()
        PurchaseLine = self.env.get("purchase.order.line")
        if PurchaseLine is None:
            return None
        account = self.analytic_account_id
        if not account:
            return self.env["purchase.order"]
        # analytic.mixin's search accepts account ids for the JSON field.
        lines = PurchaseLine.search([("analytic_distribution", "in", [account.id])])
        return lines.order_id

    def _prepare_project_values(self):
        self.ensure_one()
        values = {
            "name": self._project_name(),
            "partner_id": self.partner_id.id or False,
            "company_id": self.company_id.id or self.env.company.id,
            "allow_billable": True,
        }
        if self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        values.update(
            self._tectora_project_sync_values(
                {"planned_date_begin", "planned_date_end"}
            )
        )
        Project = self.env["project.project"]
        if "allow_timesheets" in Project._fields:
            values["allow_timesheets"] = True
        return values

    def _ensure_project(self):
        """Create (or complete) the plannable project and its analytic
        account, so revenue, costs, POs, deliveries, invoices and timesheets
        aggregate on it. Links the project to the order as well."""
        Project = self.env["project.project"].with_context(tectora_sync=True)
        for roof_project in self:
            project = roof_project.project_id
            if not project:
                # An order confirmed with project-generating services may
                # already have had its project created by Odoo: adopt it.
                order = roof_project.sale_order_id
                candidates = order.project_id if order else Project
                if order and not candidates and "project_ids" in order._fields:
                    candidates = order.sudo().project_ids.filtered(
                        lambda p: p.active and not p.roof_project_id
                    )
                project = candidates[:1]
                if project:
                    project.write(
                        {
                            key: value
                            for key, value in roof_project._prepare_project_values().items()
                            if key in ("allow_billable", "date_start", "date")
                            or not project[key]
                        }
                    )
                else:
                    project = Project.create(roof_project._prepare_project_values())
                roof_project.with_context(tectora_sync=True).project_id = project
            elif not project.partner_id and roof_project.partner_id:
                project.partner_id = roof_project.partner_id
            # sale.order.project_id only accepts billable projects.
            if not project.allow_billable:
                project.allow_billable = True
            if not project.account_id:
                project._create_analytic_account()
            roof_project._tectora_link_order_to_project(project)
        return self.mapped("project_id")

    def _tectora_link_order_to_project(self, project):
        """Point the order and the project at each other, the way Odoo's own
        sale/project bridge expects it (so its smart buttons and its
        profitability report pick the order up too)."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        order_values = {}
        if order.project_id != project:
            order_values["project_id"] = project.id
        if order_values:
            order.with_context(tectora_sync=True).write(order_values)
            # Re-trigger the analytic distribution now the project is known.
            order.order_line._compute_analytic_distribution()
        project_values = {}
        if (
            "reinvoiced_sale_order_id" in project._fields
            and not project.sudo().reinvoiced_sale_order_id
        ):
            project_values["reinvoiced_sale_order_id"] = order.id
        if "sale_line_id" in project._fields and not project.sale_line_id:
            # Not a line invoiced on timesheets: hours logged on the project
            # must not become invoiceable quantities by accident.
            service_line = order.order_line.filtered(
                lambda line: not line.display_type
                and line.product_id
                and line.product_id.type == "service"
                and not line.is_downpayment
                and getattr(line.product_id, "service_policy", None)
                != "delivered_timesheet"
            )[:1]
            if service_line and order.state == "sale":
                project_values["sale_line_id"] = service_line.id
        if project_values:
            project.sudo().with_context(tectora_sync=True).write(project_values)

    def action_open_project(self):
        """Open the project dashboard; a roof project without a project yet
        gets one (the button is the manual counterpart of the confirmation)."""
        self.ensure_one()
        self._ensure_project()
        return self.project_id.action_open_dashboard()

    def action_view_materials(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaallijst"),
            "res_model": "tectora.roof.material",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_pickings(self):
        self.ensure_one()
        pickings = self._get_pickings()
        return {
            "type": "ir.actions.act_window",
            "name": _("Leveringen"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", pickings.ids)],
        }

    def action_view_purchase_orders(self):
        self.ensure_one()
        orders = self._get_purchase_orders()
        if orders is None:
            raise UserError(_("De module Inkoop is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Inkooporders"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self.sale_order_ids.mapped("invoice_ids")
        return {
            "type": "ir.actions.act_window",
            "name": _("Facturen"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", invoices.ids)],
        }

    @api.depends("section_ids", "roof_object_ids")
    def _compute_shape_counts(self):
        for project in self:
            project.section_count = len(project.section_ids)
            project.roof_object_count = len(project.roof_object_ids)

    @api.depends(
        "section_ids.area",
        "section_ids.perimeter",
        "section_ids.product_line_ids.price_subtotal",
        "roof_object_ids.product_line_ids.price_subtotal",
        "direct_line_ids.price_subtotal",
    )
    def _compute_totals(self):
        for project in self:
            sections = project.section_ids
            project.total_area = sum(sections.mapped("area"))
            project.total_perimeter = sum(sections.mapped("perimeter"))
            project.estimated_total = sum(
                sections.product_line_ids.mapped("price_subtotal")
            ) + sum(
                project.roof_object_ids.product_line_ids.mapped("price_subtotal")
            ) + sum(project.direct_line_ids.mapped("price_subtotal"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == _("New"):
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("tectora.roof.project")
                    or _("New")
                )
        projects = super().create(vals_list)
        projects._autogenerate_planning()
        return projects

    def write(self, vals):
        result = super().write(vals)
        if {"team_id", "planned_date_begin", "planned_date_end"} & set(vals):
            self._autogenerate_planning()
        if not self.env.context.get("tectora_sync"):
            self._tectora_push_sync(vals)
        return result

    # ------------------------------------------------ sale order / project sync
    def _tectora_push_sync(self, vals):
        """Mirror the fields shared with the order and the project onto them.

        The roof project is the master here: whatever was just written on it
        goes to its order (customer, opportunity, salesperson/project manager,
        deadline, project type as pricelist) and to its project (customer,
        planned dates, project manager). The context flag stops the write from
        coming straight back.
        """
        SaleOrder = self.env["sale.order"]
        order_fields = set(SaleOrder._tectora_roof_to_order_fields())
        project_fields = {
            "partner_id", "planned_date_begin", "planned_date_end",
            "project_manager_id", "name", "code", "address",
        }
        touched = set(vals)
        for project in self:
            order = project.sale_order_id
            if order and touched & order_fields:
                order._tectora_sync_pair(project, master="roof", changed=touched)
            dossier = project.project_id
            if dossier and touched & project_fields:
                dossier.with_context(tectora_sync=True).write(
                    project._tectora_project_sync_values(touched)
                )

    def _tectora_project_sync_values(self, fields_changed=None):
        """Values of the project (project.project) that follow this roof
        project; restricted to the roof fields in ``fields_changed``."""
        self.ensure_one()
        values = {}
        changed = fields_changed or {
            "partner_id", "planned_date_begin", "planned_date_end",
            "project_manager_id", "name", "code", "address",
        }
        if "partner_id" in changed and self.partner_id:
            values["partner_id"] = self.partner_id.id
        if {"planned_date_begin", "planned_date_end"} & changed:
            begin = self.planned_date_begin
            end = self.planned_date_end
            if begin:
                values["date_start"] = fields.Datetime.context_timestamp(
                    self, begin
                ).date()
            if end:
                values["date"] = fields.Datetime.context_timestamp(self, end).date()
        if "project_manager_id" in changed and self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        if {"name", "code", "partner_id", "address"} & changed:
            values["name"] = self._project_name()
        return values

    def _site_city(self):
        """Municipality of the site: the order's delivery address, else the
        customer's, else the last part of the free-text site address
        ("Straat 1, 9790 Wortegem" -> "Wortegem")."""
        self.ensure_one()
        order = self.sale_order_id
        for partner in (order.partner_shipping_id if order else None, self.partner_id):
            if partner and partner.city:
                return partner.city.strip()
        match = re.search(r"\b\d{4,5}\s+([^,]+?)\s*$", self.address or "")
        if match:
            return match.group(1).strip()
        return ""

    def _project_name(self):
        """Name of the project: the customer and the municipality of the site
        ("Data Forge — Wortegem"); the roof project's own name as fallback."""
        self.ensure_one()
        customer = self.partner_id.name or ""
        name = " — ".join(filter(None, [customer, self._site_city()]))
        return name or self.name

    # ---------------------------------------------------------- team planning
    def _autogenerate_planning(self):
        """A project with a team and a planned window gets its work block (and
        through it the individual employee planning items) automatically.
        Existing blocks are never overwritten: use the button to add one."""
        for project in self:
            if not (
                project.team_id
                and project.planned_date_begin
                and project.planned_date_end
                and not project.planning_ids
            ):
                continue
            project._create_planning_item()
        return True

    def _create_planning_item(self):
        self.ensure_one()
        return self.env["tectora.roof.planning"].create(
            {
                "project_id": self.id,
                "team_id": self.team_id.id or False,
                "employee_ids": [(6, 0, self.team_id.member_ids.ids)],
                "start_datetime": self.planned_date_begin,
                "end_datetime": self.planned_date_end,
            }
        )

    def action_generate_planning(self):
        self.ensure_one()
        if not (self.planned_date_begin and self.planned_date_end):
            raise UserError(
                _("Vul eerst de geplande start- en einddatum van de werf in.")
            )
        if not self.team_id:
            raise UserError(_("Kies eerst de ploeg die de werf uitvoert."))
        self._create_planning_item()
        return self.action_view_planning()

    def action_view_planning(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planning"),
            "res_model": "tectora.roof.planning",
            "view_mode": "calendar,list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {
                "default_project_id": self.id,
                "default_team_id": self.team_id.id,
                "default_start_datetime": self.planned_date_begin,
                "default_end_datetime": self.planned_date_end,
            },
        }

    # -------------------------------------------------------------- map service
    def _get_map_credentials(self):
        icp = self.env["ir.config_parameter"].sudo()
        return (
            icp.get_param("tectora_roof.google_maps_api_key"),
            icp.get_param("tectora_roof.mapbox_token"),
        )

    def _geocode(self, address):
        """Return (lat, lng, formatted_address) for an address string."""
        google_key, mapbox_token = self._get_map_credentials()
        if google_key:
            response = requests.get(
                GOOGLE_GEOCODE_URL,
                params={"address": address, "key": google_key},
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if data.get("status") != "OK" or not data.get("results"):
                raise UserError(
                    _("Geocoding failed for '%(address)s': %(status)s",
                      address=address, status=data.get("status"))
                )
            result = data["results"][0]
            location = result["geometry"]["location"]
            return location["lat"], location["lng"], result["formatted_address"]
        if mapbox_token:
            response = requests.get(
                MAPBOX_GEOCODE_URL % requests.utils.quote(address),
                params={"access_token": mapbox_token, "limit": 1},
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if not data.get("features"):
                raise UserError(
                    _("No geocoding results for '%s'.") % address
                )
            feature = data["features"][0]
            lng, lat = feature["center"]
            return lat, lng, feature.get("place_name", address)
        raise UserError(
            _(
                "No mapping service configured. Set a Google Maps API key or a "
                "Mapbox access token in Settings → Tectora Dakmeting."
            )
        )

    def _fetch_static_image(self, lat, lng):
        """Fetch a satellite image centered on (lat, lng).

        Returns (png_bytes, coverage_width_px, coverage_height_px). The coverage
        size is the size the web-mercator math applies to; the actual stored
        image may be retina (@2x) and therefore larger.
        """
        google_key, mapbox_token = self._get_map_credentials()
        if google_key:
            width = height = 640  # Google Static Maps free-size maximum
            response = requests.get(
                GOOGLE_STATIC_URL,
                params={
                    "center": "%.7f,%.7f" % (lat, lng),
                    "zoom": SATELLITE_ZOOM,
                    "size": "%dx%d" % (width, height),
                    "scale": 2,  # retina: doubles resolution, not coverage
                    "maptype": "satellite",
                    "format": "png",
                    "key": google_key,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise UserError(
                    _("Google Static Maps error (HTTP %s).") % response.status_code
                )
            return response.content, width, height
        if mapbox_token:
            width = height = 1280  # Mapbox static maximum
            url = MAPBOX_STATIC_URL % {
                "lng": lng, "lat": lat, "zoom": SATELLITE_ZOOM, "w": width, "h": height,
            }
            response = requests.get(
                url,
                params={"access_token": mapbox_token},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise UserError(
                    _("Mapbox Static Images error (HTTP %s).") % response.status_code
                )
            return response.content, width, height
        raise UserError(
            _(
                "No mapping service configured. Set a Google Maps API key or a "
                "Mapbox access token in Settings → Tectora Dakmeting."
            )
        )

    def action_fetch_satellite(self):
        self.ensure_one()
        if not self.address:
            raise UserError(_("Set the site address first."))
        lat, lng, formatted = self._geocode(self.address)
        image_bytes, coverage_w, coverage_h = self._fetch_static_image(lat, lng)

        # Ground resolution of the *coverage* pixels at this latitude/zoom.
        meters_per_px = (
            EARTH_M_PER_PX * math.cos(math.radians(lat)) / (2 ** SATELLITE_ZOOM)
        )
        lat_radius = (coverage_h / 2.0) * meters_per_px / METERS_PER_DEG_LAT
        lng_radius = (coverage_w / 2.0) * meters_per_px / (
            METERS_PER_DEG_LAT * math.cos(math.radians(lat))
        )

        # The stored image may be retina (@2x): derive the scale that applies
        # to the pixels the user actually draws on.
        real_width_m = coverage_w * meters_per_px
        actual_width_px = Image.open(io.BytesIO(image_bytes)).size[0]

        self.write(
            {
                "background_image": base64.b64encode(image_bytes),
                "address": formatted,
                "bg_lat": lat,
                "bg_lng": lng,
                "bg_north": lat + lat_radius,
                "bg_south": lat - lat_radius,
                "bg_east": lng + lng_radius,
                "bg_west": lng - lng_radius,
                "scale_m_per_px": real_width_m / actual_width_px,
            }
        )
        self.message_post(
            body=_(
                "Satellite image fetched for %(address)s (scale: %(scale).4f m/px).",
                address=formatted,
                scale=self.scale_m_per_px,
            )
        )
        return True

    # ------------------------------------------------------------- canvas sync
    def _parse_canvas_shapes(self):
        self.ensure_one()
        try:
            data = json.loads(self.canvas_data or "{}")
        except (ValueError, TypeError):
            raise UserError(_("The canvas data is not valid JSON."))
        shapes = []
        for shape in data.get("shapes", []):
            points = [
                (float(p[0]), float(p[1]))
                for p in shape.get("points", [])
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            kind = shape.get("kind") or "section"
            # A seam (naad) is an open line between two roof surfaces: two
            # points are enough; everything else is a polygon.
            minimum = 2 if kind == "seam" else 3
            if len(points) >= minimum and shape.get("id"):
                def _per_edge(raw):
                    result = {}
                    for key, value in (raw or {}).items():
                        try:
                            result[int(key)] = float(value)
                        except (TypeError, ValueError):
                            continue
                    return result

                shapes.append(
                    {
                        "id": str(shape["id"]),
                        "kind": kind,
                        "name": shape.get("name") or "",
                        "points": points,
                        "edge_widths": _per_edge(shape.get("edgeWidths")),
                        "edge_upstands": _per_edge(shape.get("edgeUpstands")),
                        # A half of a section that was cut by a seam: the
                        # canvas id of the section it came from.
                        "split_from": str(shape["splitFrom"]) if shape.get("splitFrom") else None,
                    }
                )
        return shapes

    def _shape_measurements(self, points):
        scale = self.scale_m_per_px or DEFAULT_SCALE_M_PER_PX
        width_px, length_px = _bounding_box_px(points)
        return {
            "width": round(width_px * scale, 2),
            "length": round(length_px * scale, 2),
            "area": round(_polygon_area_px(points) * scale * scale, 2),
            "perimeter": round(_polygon_perimeter_px(points) * scale, 2),
        }

    def _seam_measurements(self, points):
        """A seam has a length only; it is stored as the object's length and
        perimeter, so edge products on it take the seam length."""
        scale = self.scale_m_per_px or DEFAULT_SCALE_M_PER_PX
        length_px = sum(
            math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
            for i in range(len(points) - 1)
        )
        length = round(length_px * scale, 2)
        return {"width": 0.0, "length": length, "area": 0.0, "perimeter": length}

    def _shape_inner_measurements(self, points, edge_widths):
        """Inner area/perimeter derived from per-side widths (m); zeros when
        no widths are set or the inset degenerates."""
        scale = self.scale_m_per_px or DEFAULT_SCALE_M_PER_PX
        if not edge_widths or not any(w > 0 for w in edge_widths.values()):
            return {"inner_area": 0.0, "inner_perimeter": 0.0}
        widths_px = [
            max(edge_widths.get(i, 0.0), 0.0) / scale for i in range(len(points))
        ]
        inner = _inset_polygon_px(points, widths_px)
        if not inner:
            return {"inner_area": 0.0, "inner_perimeter": 0.0}
        return {
            "inner_area": round(_polygon_area_px(inner) * scale * scale, 2),
            "inner_perimeter": round(_polygon_perimeter_px(inner) * scale, 2),
        }

    def _shape_upstand_measurements(self, points, edge_upstands):
        """Length of the sides carrying an upstand and the vertical surface
        of those upstands (per side: length x height), in m and m²."""
        scale = self.scale_m_per_px or DEFAULT_SCALE_M_PER_PX
        if not edge_upstands:
            return {"upstand_length": 0.0, "upstand_area": 0.0}
        total_length = 0.0
        total_area = 0.0
        count = len(points)
        for index in range(count):
            height = max(edge_upstands.get(index, 0.0), 0.0)
            if not height:
                continue
            ax, ay = points[index]
            bx, by = points[(index + 1) % count]
            length = math.hypot(bx - ax, by - ay) * scale
            total_length += length
            total_area += length * height
        return {
            "upstand_length": round(total_length, 2),
            "upstand_area": round(total_area, 2),
        }

    def action_sync_from_canvas(self):
        """Create/update roof sections and objects from the drawn shapes.

        Records are matched on ``canvas_ref`` so product lines assigned to a
        section survive re-syncs; records whose shape was deleted are removed.
        Manually created records (without canvas_ref) are left untouched.
        """
        self.ensure_one()
        shapes = self._parse_canvas_shapes()
        section_shapes = [s for s in shapes if s["kind"] == "section"]
        object_shapes = [s for s in shapes if s["kind"] != "section"]

        sections_by_ref = {
            s.canvas_ref: s for s in self.section_ids if s.canvas_ref
        }
        objects_by_ref = {
            o.canvas_ref: o for o in self.roof_object_ids if o.canvas_ref
        }

        section_count = 0
        for index, shape in enumerate(section_shapes, start=1):
            values = self._shape_measurements(shape["points"])
            values.update(
                self._shape_inner_measurements(
                    shape["points"], shape.get("edge_widths")
                )
            )
            values.update(
                self._shape_upstand_measurements(
                    shape["points"], shape.get("edge_upstands")
                )
            )
            values["name"] = shape["name"] or _("Sectie %s") % index
            existing = sections_by_ref.pop(shape["id"], None)
            if existing:
                existing.write(values)
            else:
                values.update({"project_id": self.id, "canvas_ref": shape["id"]})
                section = self.env["tectora.roof.section"].create(values)
                origin = sections_by_ref.get(shape.get("split_from") or "")
                if origin:
                    # Both halves of a split section inherit the products that
                    # applied to the whole surface; per-side products cannot
                    # be mapped onto the new sides and are left behind.
                    section._copy_whole_surface_lines(origin)
            section_count += 1

        object_count = 0
        for index, shape in enumerate(object_shapes, start=1):
            if shape["kind"] == "seam":
                values = self._seam_measurements(shape["points"])
                values["height"] = 0.0
            else:
                values = self._shape_measurements(shape["points"])
            values["object_type"] = shape["kind"]
            values["name"] = shape["name"] or (
                _("Naad %s") if shape["kind"] == "seam" else _("Object %s")
            ) % index
            existing = objects_by_ref.pop(shape["id"], None)
            if existing:
                existing.write(values)
            else:
                values.update({"project_id": self.id, "canvas_ref": shape["id"]})
                if shape["kind"] == "chimney":
                    values.setdefault("height", 1.5)
                self.env["tectora.roof.object"].create(values)
            object_count += 1

        # Shapes that no longer exist on the canvas.
        stale_sections = self.env["tectora.roof.section"].union(
            *sections_by_ref.values()
        ) if sections_by_ref else self.env["tectora.roof.section"]
        stale_objects = self.env["tectora.roof.object"].union(
            *objects_by_ref.values()
        ) if objects_by_ref else self.env["tectora.roof.object"]
        stale_sections.unlink()
        stale_objects.unlink()

        if self.state == "draft" and (section_count or object_count):
            self.state = "measured"
        # The quotation follows the drawing.
        self._tectora_mirror_to_order()
        # Automatic syncs from the canvas widget run on every drawing change;
        # they pass this flag so the chatter is not flooded.
        if not self.env.context.get("tectora_quiet_sync"):
            self.message_post(
                body=_(
                    "Measurement synced: %(sections)s section(s), %(objects)s "
                    "roof object(s).",
                    sections=section_count,
                    objects=object_count,
                )
            )
        return True

    # ----------------------------------------------------- measurement sheet
    def _project_type_label(self):
        self.ensure_one()
        return dict(self._fields["project_type"].selection).get(self.project_type, "")

    def _get_drawing_b64(self):
        """Base64 PNG of the drawing for the measurement sheet: the snapshot
        stored by the canvas widget, or a server-side render as fallback.
        Returns bytes (image_data_uri decodes them itself); never raises —
        without a drawing the sheet renders without image."""
        self.ensure_one()
        if self.canvas_snapshot:
            snapshot = self.canvas_snapshot
            return snapshot if isinstance(snapshot, bytes) else snapshot.encode()
        try:
            return self._render_drawing_fallback_b64()
        except Exception:
            _logger.exception(
                "Could not render the fallback drawing for %s", self.code
            )
            return False

    def _render_drawing_fallback_b64(self):
        self.ensure_one()
        try:
            shapes = self._parse_canvas_shapes()
        except UserError:
            shapes = []
        if self.background_image:
            base = Image.open(
                io.BytesIO(base64.b64decode(self.background_image))
            ).convert("RGBA")
        else:
            xs = [p[0] for s in shapes for p in s["points"]] or [0.0, 1400.0]
            ys = [p[1] for s in shapes for p in s["points"]] or [0.0, 900.0]
            width = max(int(max(xs)) + 60, 200)
            height = max(int(max(ys)) + 60, 150)
            base = Image.new("RGBA", (width, height), (246, 248, 249, 255))
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        fills = {
            "section": (10, 116, 131, 80),
            "chimney": (217, 119, 6, 90),
            "skylight": (37, 99, 235, 80),
        }
        strokes = {
            "section": (10, 116, 131, 255),
            "chimney": (180, 83, 9, 255),
            "skylight": (29, 78, 216, 255),
        }
        try:
            font = ImageFont.load_default(size=max(14, base.size[0] // 80))
        except TypeError:  # Pillow < 10.1 has no size parameter
            font = ImageFont.load_default()
        for shape in shapes:
            points = [tuple(p) for p in shape["points"]]
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            if shape["kind"] == "seam":
                # Dotted line: PIL has no dash pattern, so draw the dashes.
                seam_color = (55, 65, 81, 255)
                for (ax, ay), (bx, by) in zip(points, points[1:]):
                    total = math.hypot(bx - ax, by - ay) or 1.0
                    dash, gap, pos = 8.0, 6.0, 0.0
                    while pos < total:
                        end = min(pos + dash, total)
                        draw.line(
                            [
                                (ax + (bx - ax) * pos / total, ay + (by - ay) * pos / total),
                                (ax + (bx - ax) * end / total, ay + (by - ay) * end / total),
                            ],
                            fill=seam_color,
                            width=3,
                        )
                        pos += dash + gap
                measures = self._seam_measurements(shape["points"])
                label = "%s\nnaad %.1f m" % (shape["name"] or "", measures["length"])
                draw.multiline_text(
                    (cx, cy), label.strip(), fill=(11, 31, 36, 255),
                    font=font, anchor="mm", align="center",
                )
                continue
            kind = shape["kind"] if shape["kind"] in fills else "section"
            draw.polygon(points, fill=fills[kind])
            draw.line(points + [points[0]], fill=strokes[kind], width=3)
            measures = self._shape_measurements(shape["points"])
            label = "%s\n%.1f × %.1f m — %.1f m²" % (
                shape["name"] or "",
                measures["width"],
                measures["length"],
                measures["area"],
            )
            draw.multiline_text(
                (cx, cy), label.strip(), fill=(11, 31, 36, 255),
                font=font, anchor="mm", align="center",
            )
        image = Image.alpha_composite(base, overlay).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue())

    # ------------------------------------------------------------- quotation
    def _measurement_order_lines(self):
        """The measurement part of the quotation: per roof section and roof
        object a header and the assigned products, one line per (product,
        coverage) with the quantities summed over the sides.

        Returns a list of (header name, [line values]).
        """
        self.ensure_one()

        def aggregated_order_lines(lines):
            grouped = {}
            for line in lines:
                key = (line.product_id.id, line.coverage)
                entry = grouped.setdefault(
                    key, {"first": line, "quantity": 0.0, "sides": set()}
                )
                entry["quantity"] += line.quantity
                if line.edge_index:
                    entry["sides"].add(line.edge_index)
            values = []
            for (_product_id, coverage), entry in grouped.items():
                first = entry["first"]
                name = first.product_id.display_name
                if coverage != "general":
                    label = dict(first._fields["coverage"].selection).get(
                        coverage, coverage
                    )
                    sides = sorted(entry["sides"])
                    if sides:
                        if coverage == "corners":
                            position = _("hoek") if len(sides) == 1 else _("hoeken")
                        else:
                            position = _("zijde") if len(sides) == 1 else _("zijden")
                        label = "%s, %s %s" % (
                            label, position, ", ".join(str(s) for s in sides),
                        )
                    name = "%s (%s)" % (name, label)
                values.append({
                    "product_id": first.product_id.id,
                    "product_uom_qty": entry["quantity"],
                    "name": name,
                })
            return values

        blocks = []
        for target in self.section_ids.filtered("product_line_ids"):
            blocks.append((
                "%s — %.2f m², omtrek %.2f m" % (
                    target.name, target.area, target.perimeter,
                ),
                aggregated_order_lines(target.product_line_ids),
            ))
        for target in self.roof_object_ids.filtered("product_line_ids"):
            if target.object_type == "seam":
                header = "%s — naad %.2f m" % (target.name, target.perimeter)
            else:
                header = "%s — %.2f m², omtrek %.2f m" % (
                    target.name, target.area, target.perimeter,
                )
            blocks.append((header, aggregated_order_lines(target.product_line_ids)))
        return blocks

    # ------------------------------------------------- quotation mirroring
    @api.model
    def _chapter_of(self, category):
        """The chapter (top category under the root, "04. Opbouwwerken plat
        dak") a category belongs to, and its label without the number."""
        chapter = category
        while chapter.parent_id and chapter.parent_id.parent_id:
            chapter = chapter.parent_id
        if not re.match(r"^\d+\.", chapter.name or "") and category.name:
            chapter = category
        label = re.sub(r"^\d+\.\s*", "", chapter.name or _("Overige"))
        return chapter, label

    @api.model
    def _header_matches(self, header_name, label):
        """Whether an existing section header on the quotation is the
        chapter ``label``: equal names, or a shared stem ("Dakopbouw" for
        "Opbouwwerken plat dak", "Veiligheid" for "Verplichte
        veiligheidsvoorzieningen")."""
        header = (header_name or "").strip().lower()
        wanted = label.strip().lower()
        if not header or not wanted:
            return False
        if header == wanted:
            return True
        stop = {"werken", "plat", "dak", "en", "van", "de", "het", "verplichte"}
        for token in re.findall(r"[a-zà-ÿ]+", wanted):
            if len(token) >= 5 and token not in stop:
                stem = token[:6]
                if stem in header:
                    return True
        return False

    def _tectora_mirror_to_order(self, order=None):
        """Roof project -> open quotation.

        Chapter lines (project level) each keep one order line under the
        header of their chapter, with the quantity of the roof project; the
        measurement lines (sections, objects) are rebuilt from the drawing.
        Lines the user added to the quotation by hand are left alone. A
        chapter line for a product the drawing now prices is dropped, so
        nothing is counted twice.
        """
        Line = self.env["sale.order.line"].with_context(tectora_sync=True)
        for project in self:
            target = order or project.sale_order_id
            if not target or target.state not in ("draft", "sent"):
                continue
            target = target.with_context(tectora_sync=True)
            measured_products = (
                project.section_ids.product_line_ids
                | project.roof_object_ids.product_line_ids
            ).product_id
            superseded = project.direct_line_ids.filtered(
                lambda line: line.product_id in measured_products
            )
            if superseded:
                superseded.with_context(tectora_sync=True).unlink()

            lines = target.order_line.sorted(lambda l: (l.sequence, l.id))
            by_roof_line = {}
            for line in lines:
                if line.roof_line_id:
                    by_roof_line.setdefault(line.roof_line_id, line)

            # Chapter lines.
            for roof_line in project.direct_line_ids:
                line = by_roof_line.get(roof_line)
                if line:
                    values = {}
                    if line.product_id != roof_line.product_id:
                        values["product_id"] = roof_line.product_id.id
                    if roof_line._quantity_differs(line.product_uom_qty):
                        values["product_uom_qty"] = roof_line.quantity
                    if values:
                        line.with_context(tectora_sync=True).write(values)
                    continue
                _chapter, label = self._chapter_of(roof_line.product_id.categ_id)
                header = lines.filtered(
                    lambda l: l.display_type == "line_section"
                    and self._header_matches(l.name, label)
                )[:1]
                if not header:
                    header = Line.create({
                        "order_id": target.id,
                        "display_type": "line_section",
                        "name": label,
                        "sequence": (max(lines.mapped("sequence")) if lines else 0) + 10,
                    })
                    lines |= header
                # Right behind the last line of that chapter block.
                block_end = header
                for line in lines.sorted(lambda l: (l.sequence, l.id)):
                    if (line.sequence, line.id) <= (header.sequence, header.id):
                        continue
                    if line.display_type == "line_section":
                        break
                    block_end = line
                new_line = Line.create({
                    "order_id": target.id,
                    "product_id": roof_line.product_id.id,
                    "product_uom_qty": roof_line.quantity,
                    "roof_line_id": roof_line.id,
                    "sequence": block_end.sequence,
                })
                # Keep it after block_end when sequences tie: resequenced below.
                lines = self._insert_after(lines, block_end, new_line)

            # Measurement lines: rebuilt every time.
            stale = lines.filtered("roof_measurement_line")
            lines -= stale
            if stale:
                stale.unlink()
            ordered = list(lines.sorted(lambda l: (l.sequence, l.id)))
            for header_name, values_list in project._measurement_order_lines():
                ordered.append(Line.create({
                    "order_id": target.id,
                    "display_type": "line_section",
                    "name": header_name,
                    "roof_measurement_line": True,
                }))
                for values in values_list:
                    values.update({"order_id": target.id, "roof_measurement_line": True})
                    ordered.append(Line.create(values))
            # One clean sequence for the whole quotation.
            for index, line in enumerate(ordered, start=1):
                if line.sequence != index * 10:
                    line.with_context(tectora_sync=True).write({"sequence": index * 10})
        return True

    @api.model
    def _insert_after(self, lines, anchor, new_line):
        """Recordset ``lines`` with ``new_line`` placed right after ``anchor``
        (order carried by the recordset itself, sequences set afterwards)."""
        result = self.env["sale.order.line"]
        inserted = False
        for line in lines:
            result |= line
            if line == anchor:
                result |= new_line
                inserted = True
        if not inserted:
            result |= new_line
        return result

    def _find_pricelist(self):
        """Pricelist named after the project type, if the company has one."""
        self.ensure_one()
        if not self.project_type:
            return self.env["product.pricelist"]
        type_label = dict(self._fields["project_type"].selection)[self.project_type]
        return self.env["product.pricelist"].search(
            [
                ("name", "=ilike", type_label),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            limit=1,
        )

    def _prepare_sale_order_values(self):
        self.ensure_one()
        values = {
            "partner_id": self.partner_id.id,
            "opportunity_id": self.opportunity_id.id or False,
            "origin": self.code,
            "roof_project_id": self.id,
            "company_id": self.company_id.id or self.env.company.id,
        }
        if self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        if self.project_id:
            values["project_id"] = self.project_id.id
        pricelist = self._find_pricelist()
        if pricelist:
            values["pricelist_id"] = pricelist.id
        return values

    def action_create_sale_order(self):
        """Create the quotation of the roof project, or bring it in line with
        the measurement.

        One roof project stands against one order: an open quotation is
        aligned (chapter lines and measurement lines follow the roof project,
        manual lines stay), a confirmed order is left alone, and only when
        there is no open order a new quotation is created.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Set a customer on the project first."))
        order = self.sale_order_id
        if order and order.state == "cancel":
            order = self.env["sale.order"]
        if order and order.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "Order %(order)s van dit dakproject is al bevestigd. Pas de "
                    "order zelf aan, of annuleer ze en maak een nieuwe offerte.",
                    order=order.name,
                )
            )
        if not order:
            if not (
                self.direct_line_ids
                or self.section_ids.product_line_ids
                or self.roof_object_ids.product_line_ids
            ):
                raise UserError(
                    _(
                        "No products are assigned to any roof section, roof "
                        "object or project tab yet. Add product lines first."
                    )
                )
            order = self.env["sale.order"].with_context(tectora_sync=True).create(
                self._prepare_sale_order_values()
            )
            self.message_post(
                body=_(
                    "Quotation %s created from the roof measurement.",
                    order._get_html_link(),
                )
            )
        else:
            self.message_post(
                body=_(
                    "Quotation %s refreshed from the roof measurement.",
                    order._get_html_link(),
                )
            )
        self._tectora_mirror_to_order(order)
        # The meetblad is rendered as an extra page inside the quotation PDF
        # itself (see report_saleorder_inherit_tectora), so no separate
        # attachment is created here.
        if self.state in ("draft", "measured"):
            self.with_context(tectora_sync=True).state = "quoted"
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_order(self):
        """The order of this roof project; a new quotation when there is
        none yet (the smart button is always there)."""
        self.ensure_one()
        order = self.sale_order_id
        if order:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": order.id,
                "view_mode": "form",
                "target": "current",
            }
        context = {
            "default_%s" % key: value
            for key, value in self._prepare_sale_order_values().items()
        }
        return {
            "type": "ir.actions.act_window",
            "name": _("Offerte"),
            "res_model": "sale.order",
            "view_mode": "form",
            "target": "current",
            "context": context,
        }

    def action_view_sale_orders(self):
        """History of every quotation/order of this roof project."""
        self.ensure_one()
        if len(self.sale_order_ids) <= 1:
            return self.action_view_sale_order()
        return {
            "type": "ir.actions.act_window",
            "name": _("Offertes / Orders"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("roof_project_id", "=", self.id)],
            "context": {
                "default_roof_project_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }
