# -*- coding: utf-8 -*-
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

# The vapour barrier runs up every upstand and around every roof object to
# above the insulation: its thickness plus this much (m).
VAPOUR_UPSTAND_EXTRA = 0.05


def is_vapour_barrier(product):
    """Whether ``product`` is a vapour barrier (dampscherm)."""
    if not product:
        return False
    text = "%s %s" % (product.name or "", product.categ_id.complete_name or "")
    return bool(re.search(r"dampscherm|dampopen", text.lower()))


def is_kimfix(product):
    """Whether ``product`` is the kimfixatie (the mechanical fixing of the
    EPDM at the foot of the upstands)."""
    return bool(product) and "kimfix" in (product.name or "").lower()


def is_insulation(product):
    """Whether ``product`` is roof insulation that is laid (not removed)."""
    if not product:
        return False
    name = (product.name or "").lower()
    return "isolatie" in name and not re.search(r"verwijder|afbraak|afvoer", name)


def insulation_thickness(product):
    """The thickness (m) of an insulation product, from its name ("...
    isolatie type: ... dikte: 10cm ..."), or 0."""
    name = (product.name or "").lower() if product else ""
    if "isolatie" not in name:
        return 0.0
    match = re.search(r"dikte:\s*([\d.,]+)\s*(mm|cm)", name)
    if not match:
        return 0.0
    value = float(match.group(1).replace(",", "."))
    return value / 1000.0 if match.group(2) == "mm" else value / 100.0


COVERAGE_SELECTION = [
    ("surface", "Oppervlak"),
    ("edges", "Randen"),
    ("corners", "Hoeken"),
    ("drainage", "Afvoer"),
    ("general", "Algemeen"),
]


class TectoraRoofSection(models.Model):
    _name = "tectora.roof.section"
    _description = "Roof Section"
    _order = "project_id, id"

    name = fields.Char(string="Naam", required=True)
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Project",
        required=True,
        ondelete="cascade",
        index=True,
    )
    roof_id = fields.Many2one(
        "tectora.roof.project.roof",
        string="Dak",
        ondelete="cascade",
        index=True,
        domain="[('project_id', '=', project_id)]",
        help="Het dak op wiens plan deze sectie getekend is.",
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id")
    canvas_ref = fields.Char(
        string="Canvas ID",
        readonly=True,
        copy=False,
        help="Identifier of the shape on the drawing canvas this section was "
        "created from. Sections without a canvas reference were added manually "
        "and are never touched by the canvas sync.",
    )
    width = fields.Float(string="Breedte (m)", digits=(16, 2))
    length = fields.Float(string="Lengte (m)", digits=(16, 2))
    area = fields.Float(string="Oppervlakte (m²)", digits=(16, 2))
    perimeter = fields.Float(string="Omtrek (m)", digits=(16, 2))
    inner_area = fields.Float(
        string="Binnenopp. (m²)",
        digits=(16, 2),
        help="Oppervlakte binnen de randen, berekend uit de per zijde "
        "ingestelde randbreedtes op de tekening.",
    )
    inner_perimeter = fields.Float(string="Binnenomtrek (m)", digits=(16, 2))
    upstand_length = fields.Float(
        string="Opstandlengte (m)",
        digits=(16, 2),
        help="Totale lengte van de zijden waarop een opstand is ingesteld.",
    )
    upstand_area = fields.Float(
        string="Opstandopp. (m²)",
        digits=(16, 2),
        help="Verticale oppervlakte van de opstanden: per zijde de lengte "
        "maal de ingestelde opstandhoogte.",
    )
    object_area = fields.Float(
        string="Opp. dakobjecten (m²)",
        digits=(16, 2),
        help="Oppervlakte van de dakobjecten (koepels, schoorstenen, ...) op "
        "deze sectie: niet onder het dampscherm.",
    )
    object_perimeter = fields.Float(
        string="Omtrek dakobjecten (m)",
        digits=(16, 2),
        help="Omtrek van de dakobjecten op deze sectie: het dampscherm loopt "
        "er rondom op tot boven de isolatie.",
    )
    kimfix_object_perimeter = fields.Float(
        string="Omtrek schoorstenen en koepels (m)",
        digits=(16, 2),
        help="Omtrek van de schoorstenen en koepels op deze sectie: de "
        "kimfixatie loopt er rondom.",
    )
    description = fields.Text(string="Omschrijving")
    product_line_ids = fields.One2many(
        "tectora.roof.section.product", "section_id", string="Producten"
    )
    estimated_total = fields.Monetary(
        string="Geschat totaal",
        compute="_compute_estimated_total",
        currency_field="currency_id",
    )

    def _tectora_insulation_thickness(self):
        """The thickness (m) of the insulation on this surface (the thickest
        if there are several), 0 without."""
        self.ensure_one()
        lines = self.product_line_ids.filtered(lambda l: l.coverage == "surface" and not l.edge_index)
        return max([insulation_thickness(line.product_id) for line in lines] or [0.0])

    def _tectora_kimfix_quantity(self):
        """The kimfixatie of this surface (m): all its sides (at the foot of
        the upstands, the surface inside the roof edges) and around its
        chimneys and domes."""
        self.ensure_one()
        return round((self.inner_perimeter or self.perimeter) + self.kimfix_object_perimeter, 2)

    def _tectora_insulation_quantity(self):
        """The insulation of this surface (m²): the surface inside the roof
        edges, less the roof objects on it."""
        self.ensure_one()
        return round(max((self.inner_area or self.area) - self.object_area, 0.0), 2)

    def _tectora_vapour_quantity(self, thickness=None):
        """The vapour barrier of this surface (m²): the surface inside the
        roof edges, less the roof objects on it, plus where it runs up -- the
        upstands and around the objects -- the insulation's thickness + 5 cm.
        Returns the figures behind it too."""
        self.ensure_one()
        if thickness is None:
            thickness = self._tectora_insulation_thickness()
        surface = self.inner_area or self.area
        height = thickness + VAPOUR_UPSTAND_EXTRA
        up_length = self.upstand_length + self.object_perimeter
        quantity = max(surface - self.object_area, 0.0) + up_length * height
        return {
            "quantity": round(quantity, 2),
            "surface": round(surface, 2),
            "object_area": round(self.object_area, 2),
            "upstand_length": round(self.upstand_length, 2),
            "object_perimeter": round(self.object_perimeter, 2),
            "thickness": round(thickness, 3),
            "height": round(height, 3),
        }

    @api.depends("product_line_ids.price_subtotal")
    def _compute_estimated_total(self):
        for section in self:
            section.estimated_total = sum(
                section.product_line_ids.mapped("price_subtotal")
            )

    # ------------------------------------------------------------ seam split
    def _copy_whole_surface_lines(self, origin):
        """Take over the product lines of ``origin`` that apply to the whole
        surface (no side number): surface, edge, corner and drainage products.
        Quantities follow this section's own measurement."""
        self.ensure_one()
        Line = self.env["tectora.roof.section.product"].with_context(tectora_sync=True)
        values = []
        for line in origin.product_line_ids.filtered(lambda l: not l.edge_index):
            values.append({
                "section_id": self.id,
                "product_id": line.product_id.id,
                "coverage": line.coverage,
                "quantity": line.quantity,
                "edge_index": 0,
            })
        return Line.create(values) if values else Line

    # --------------------------------------------------- convert to roof object
    def write(self, vals):
        """A measurement typed by hand (area, perimeter) moves the measured
        quantities of the section's lines and of the chapter lines, so the
        open quotation must follow, the way it does after a drawing sync."""
        result = super().write(vals)
        if not self.env.context.get("tectora_sync") and (
            {"area", "perimeter", "inner_area", "inner_perimeter", "upstand_area"} & set(vals)
        ):
            self.project_id._tectora_mirror_to_order()
        return result

    def action_convert_to_chimney(self):
        return self._convert_to_object("chimney")

    def action_convert_to_skylight(self):
        return self._convert_to_object("skylight")

    def _convert_to_object(self, object_type):
        """Turn this section into a roof object (chimney/skylight).

        Mirrors the legacy behaviour: the object inherits the section's
        geometry, chimneys get a default 1.5 m height, and the section itself
        is removed. The corresponding canvas shape is re-tagged so the drawing
        stays consistent.
        """
        self.ensure_one()
        project = self.project_id
        roof_object = self.env["tectora.roof.object"].create(
            {
                "project_id": project.id,
                "roof_id": self.roof_id.id,
                "name": self.name,
                "object_type": object_type,
                "width": self.width,
                "length": self.length,
                "area": self.area,
                "perimeter": self.perimeter,
                "height": 1.5 if object_type == "chimney" else 0.0,
                "canvas_ref": self.canvas_ref,
                "description": self.description,
            }
        )
        if self.canvas_ref and project.canvas_data:
            try:
                data = json.loads(project.canvas_data)
            except (ValueError, TypeError):
                data = None
            if data:
                for shape in data.get("shapes", []):
                    if str(shape.get("id")) == self.canvas_ref:
                        shape["kind"] = object_type
                project.canvas_data = json.dumps(data)
        label = dict(roof_object._fields["object_type"].selection).get(object_type)
        project.message_post(
            body=_(
                "Section '%(name)s' converted to %(kind)s.",
                name=self.name,
                kind=label,
            )
        )
        self.unlink()
        return True


class TectoraRoofSectionProduct(models.Model):
    """A product on a roof section, a roof object or the project as a whole.

    The quantity follows the measurement: a surface product takes the area,
    an edge product the perimeter -- of the section, or of the whole roof for
    a project-level (chapter) line. Every line is mirrored on the open
    quotation of the roof project, so the order follows the drawing.
    """

    _name = "tectora.roof.section.product"
    _description = "Roof Section Product Line"

    section_id = fields.Many2one(
        "tectora.roof.section",
        string="Sectie",
        ondelete="cascade",
        index=True,
    )
    object_id = fields.Many2one(
        "tectora.roof.object",
        string="Dakobject",
        ondelete="cascade",
        index=True,
    )
    project_direct_id = fields.Many2one(
        "tectora.roof.project",
        string="Project (rechtstreeks)",
        ondelete="cascade",
        index=True,
        help="Set for product lines that belong to the project as a whole "
        "(Algemene werken, Veiligheid) instead of to a section or object.",
    )
    project_id = fields.Many2one(
        "tectora.roof.project", compute="_compute_project_id", store=True
    )
    roof_id = fields.Many2one(
        "tectora.roof.project.roof",
        string="Dak",
        ondelete="cascade",
        index=True,
        help="Voor een projectlijn van één dak: de hoeveelheid volgt de "
        "oppervlakte of omtrek van dat dak in plaats van het hele project.",
    )
    currency_id = fields.Many2one(related="project_id.currency_id")
    edge_index = fields.Integer(
        string="Zijde nr.",
        help="1-based number of the side of the shape this product applies to; "
        "0 means the product applies to the whole shape.",
    )
    side_display = fields.Char(string="Zijde", compute="_compute_side_display")
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("sale_ok", "=", True)],
    )
    coverage = fields.Selection(
        COVERAGE_SELECTION,
        string="Toepassing",
        required=True,
        default="surface",
        help="Determines the default quantity: surface uses the section area "
        "(m²), edges use the perimeter (m), corners default to 4 pieces and "
        "drainage to 1 piece.",
    )
    quantity = fields.Float(
        string="Hoeveelheid",
        digits="Product Unit of Measure",
        compute="_compute_quantity",
        store=True,
        readonly=False,
        help="Volgt de meting: oppervlakte (m²) of omtrek (m) van de sectie, "
        "of van het hele dak voor een projectlijn. Een ingevoerde waarde "
        "blijft staan tot de tekening verandert.",
    )
    sale_line_ids = fields.One2many(
        "sale.order.line", "roof_line_id", string="Offertelijnen",
        help="Lijnen op de offerte die deze projectlijn spiegelen.",
    )
    uom_id = fields.Many2one(related="product_id.uom_id", string="Eenheid")
    price_unit = fields.Float(
        related="product_id.lst_price", string="Eenheidsprijs"
    )
    price_subtotal = fields.Monetary(
        string="Subtotaal (excl. btw)",
        compute="_compute_price_subtotal",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("section_id.project_id", "object_id.project_id", "project_direct_id")
    def _compute_project_id(self):
        for line in self:
            line.project_id = (
                line.section_id.project_id
                or line.object_id.project_id
                or line.project_direct_id
            )

    @api.depends("edge_index", "coverage")
    def _compute_side_display(self):
        for line in self:
            if not line.edge_index:
                line.side_display = ""
            elif line.coverage == "corners":
                line.side_display = _("Hoek %s") % line.edge_index
            else:
                line.side_display = _("Zijde %s") % line.edge_index

    @api.constrains("section_id", "object_id", "project_direct_id")
    def _check_target(self):
        for line in self:
            targets = [
                bool(line.section_id),
                bool(line.object_id),
                bool(line.project_direct_id),
            ]
            if sum(targets) != 1:
                raise ValidationError(
                    _(
                        "A product line must be linked to exactly one target: "
                        "a roof section, a roof object or the project itself."
                    )
                )

    @api.depends("quantity", "product_id.lst_price")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.product_id.lst_price

    @api.depends(
        "coverage", "edge_index",
        "section_id.area", "section_id.perimeter",
        "section_id.inner_area", "section_id.upstand_length",
        "section_id.object_area", "section_id.object_perimeter",
        "section_id.inner_perimeter", "section_id.kimfix_object_perimeter",
        "section_id.product_line_ids.product_id",
        "object_id.area", "object_id.perimeter", "object_id.height", "product_id",
        "project_direct_id.total_area", "project_direct_id.total_perimeter",
        "roof_id.total_area", "roof_id.total_perimeter",
    )
    def _compute_quantity(self):
        """Quantity from the measurement. Per-side lines keep the length the
        drawing gave them; corners, drainage and general lines keep what was
        entered (defaults 4 and 1)."""
        from .roof_skylux import chimney_area, chimney_cladding  # noqa: PLC0415
        for line in self:
            if line.edge_index:
                line.quantity = line.quantity or 1.0
                continue
            if line.project_direct_id:
                # A line of one roof follows that roof, as soon as its plan is
                # drawn; until then it keeps the quantity it was given.
                measure = line.roof_id or line.project_direct_id
                if line.roof_id and not line.roof_id.total_area:
                    line.quantity = line.quantity or 1.0
                elif line.coverage == "surface":
                    line.quantity = measure.total_area
                elif line.coverage == "edges":
                    line.quantity = measure.total_perimeter
                else:
                    line.quantity = line.quantity or 1.0
                continue
            target = line.section_id or line.object_id
            if line.section_id and line.coverage == "surface" and is_vapour_barrier(line.product_id):
                # The vapour barrier: inner surface less the objects, plus
                # up the upstands and around the objects.
                line.quantity = line.section_id._tectora_vapour_quantity()["quantity"]
            elif line.section_id and line.coverage == "surface" and is_insulation(line.product_id):
                # The insulation: inner surface less the objects.
                line.quantity = line.section_id._tectora_insulation_quantity()
            elif line.section_id and line.coverage == "edges" and is_kimfix(line.product_id):
                # The kimfixatie: every side, and around chimneys and domes.
                line.quantity = line.section_id._tectora_kimfix_quantity()
            elif line.object_id and line.coverage == "surface" and chimney_cladding(line.product_id):
                # A chimney's cladding: its sides (and its top).
                line.quantity = chimney_area(line.object_id, line.product_id)
            elif target and line.coverage == "surface":
                line.quantity = target.area
            elif target and line.coverage == "edges":
                line.quantity = target.perimeter
            elif line.coverage == "corners":
                line.quantity = line.quantity or 4.0
            else:
                line.quantity = line.quantity or 1.0

    @api.onchange("product_id")
    def _onchange_product_id(self):
        """A chapter line picked in one of the project tabs is measured by
        the unit of its product (m² -> surface, m -> edges, else counted)."""
        for line in self:
            if line.product_id and (line.project_direct_id or not (line.section_id or line.object_id)):
                line.coverage = self._coverage_from_product(line.product_id)

    # ----------------------------------------------------------- unit -> use
    @api.model
    def _coverage_from_product(self, product):
        """How a product is measured, read off its unit: m² -> surface,
        m -> edges, anything else is counted (general)."""
        uom = product.uom_id
        if not uom:
            return "general"
        root = uom
        seen = set()
        while (
            "relative_uom_id" in root._fields
            and root.relative_uom_id
            and root.id not in seen
        ):
            seen.add(root.id)
            root = root.relative_uom_id
        square = self.env.ref("uom.product_uom_square_meter", raise_if_not_found=False)
        meter = self.env.ref("uom.product_uom_meter", raise_if_not_found=False)
        if square and (uom == square or root == square):
            return "surface"
        if meter and (uom == meter or root == meter):
            return "edges"
        if "category_id" in uom._fields and uom.category_id:
            for candidate, coverage in ((square, "surface"), (meter, "edges")):
                if candidate and uom.category_id == candidate.category_id:
                    return coverage
        name = (uom.name or "").strip().lower()
        if name in ("m²", "m2", "m^2", "vierkante meter"):
            return "surface"
        if name in ("m", "lm", "meter", "lopende meter"):
            return "edges"
        return "general"

    # ------------------------------------------------------ order mirroring
    @api.model_create_multi
    def create(self, vals_list):
        Product = self.env["product.product"]
        for vals in vals_list:
            # A chapter line (project level) is measured by its unit unless
            # the caller said otherwise.
            if vals.get("project_direct_id") and not vals.get("coverage") and vals.get("product_id"):
                vals["coverage"] = self._coverage_from_product(
                    Product.browse(vals["product_id"])
                )
        lines = super().create(vals_list)
        if not self.env.context.get("tectora_sync"):
            lines.project_id._tectora_mirror_to_order()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("tectora_sync") and (
            {"quantity", "product_id", "coverage", "edge_index"} & set(vals)
        ):
            self.project_id._tectora_mirror_to_order()
        return result

    def unlink(self):
        """A removed line leaves the open quotation as well when the quotation
        follows the measurement; the measurement lines of the quotation are
        rebuilt afterwards."""
        projects = self.project_id
        order_lines = self.sale_line_ids.filtered(
            lambda line: line.order_id.state in ("draft", "sent")
            and line.order_id.tectora_follow_measurement
        )
        if order_lines:
            order_lines.with_context(tectora_sync=True).unlink()
        result = super().unlink()
        if not self.env.context.get("tectora_sync"):
            projects.exists()._tectora_mirror_to_order()
        return result

    def _quantity_differs(self, quantity):
        self.ensure_one()
        # Odoo 20 rounds every unit on the "Product Unit" precision (what
        # uom.compare does, which needs a unit; a line may have no product).
        digits = self.env["decimal.precision"].precision_get("Product Unit")
        return float_compare(self.quantity, quantity, precision_digits=digits) != 0
