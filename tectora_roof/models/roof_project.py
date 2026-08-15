# -*- coding: utf-8 -*-
import base64
import io
import json
import math

import requests
from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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


class TectoraRoofProject(models.Model):
    _name = "tectora.roof.project"
    _description = "Roof Measurement Project"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

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
            ("done", "Afgerond"),
        ],
        default="draft",
        tracking=True,
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
        help="Geographic scale of the drawing: how many meters one canvas pixel "
        "represents. Set automatically when a satellite image is fetched; can be "
        "corrected manually when working from an uploaded plan.",
    )

    # --- Drawing --------------------------------------------------------------
    canvas_data = fields.Text(
        string="Tekening (JSON)",
        default='{"shapes": []}',
        help="Shapes drawn on the canvas, in image-pixel coordinates.",
    )

    section_ids = fields.One2many(
        "tectora.roof.section", "project_id", string="Daksecties"
    )
    roof_object_ids = fields.One2many(
        "tectora.roof.object", "project_id", string="Dakobjecten"
    )
    sale_order_ids = fields.One2many(
        "sale.order", "roof_project_id", string="Offertes / Orders"
    )
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")

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

    def _compute_sale_order_count(self):
        for project in self:
            project.sale_order_count = len(project.sale_order_ids)

    @api.depends(
        "section_ids.area",
        "section_ids.perimeter",
        "section_ids.product_line_ids.price_subtotal",
    )
    def _compute_totals(self):
        for project in self:
            sections = project.section_ids
            project.total_area = sum(sections.mapped("area"))
            project.total_perimeter = sum(sections.mapped("perimeter"))
            project.estimated_total = sum(
                sections.product_line_ids.mapped("price_subtotal")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == _("New"):
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("tectora.roof.project")
                    or _("New")
                )
        return super().create(vals_list)

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
            if len(points) >= 3 and shape.get("id"):
                shapes.append(
                    {
                        "id": str(shape["id"]),
                        "kind": shape.get("kind") or "section",
                        "name": shape.get("name") or "",
                        "points": points,
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
            values["name"] = shape["name"] or _("Sectie %s") % index
            existing = sections_by_ref.pop(shape["id"], None)
            if existing:
                existing.write(values)
            else:
                values.update({"project_id": self.id, "canvas_ref": shape["id"]})
                self.env["tectora.roof.section"].create(values)
            section_count += 1

        object_count = 0
        for index, shape in enumerate(object_shapes, start=1):
            values = self._shape_measurements(shape["points"])
            values["object_type"] = shape["kind"]
            values["name"] = shape["name"] or _("Object %s") % index
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
        self.message_post(
            body=_(
                "Measurement synced: %(sections)s section(s), %(objects)s roof "
                "object(s).",
                sections=section_count,
                objects=object_count,
            )
        )
        return True

    # ------------------------------------------------------------- quotation
    def action_create_sale_order(self):
        """Generate a native quotation from the measured sections."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Set a customer on the project first."))
        sections = self.section_ids.filtered("product_line_ids")
        if not sections:
            raise UserError(
                _(
                    "No products are assigned to any roof section yet. Add "
                    "product lines on the sections first."
                )
            )

        order_lines = []
        for section in sections:
            order_lines.append(
                (0, 0, {
                    "display_type": "line_section",
                    "name": "%s — %.2f m², omtrek %.2f m" % (
                        section.name, section.area, section.perimeter,
                    ),
                })
            )
            for line in section.product_line_ids:
                order_lines.append(
                    (0, 0, {
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.quantity,
                        "name": "%s (%s)" % (
                            line.product_id.display_name,
                            dict(line._fields["coverage"].selection).get(
                                line.coverage, line.coverage
                            ),
                        ),
                    })
                )

        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_id.id,
                "opportunity_id": self.opportunity_id.id or False,
                "origin": self.code,
                "roof_project_id": self.id,
                "order_line": order_lines,
            }
        )
        self.state = "quoted"
        self.message_post(
            body=_(
                "Quotation %s created from the roof measurement.",
                order._get_html_link(),
            )
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_orders(self):
        self.ensure_one()
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
