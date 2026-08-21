# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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
    description = fields.Text(string="Omschrijving")
    product_line_ids = fields.One2many(
        "tectora.roof.section.product", "section_id", string="Producten"
    )
    estimated_total = fields.Monetary(
        string="Geschat totaal",
        compute="_compute_estimated_total",
        currency_field="currency_id",
    )

    @api.depends("product_line_ids.price_subtotal")
    def _compute_estimated_total(self):
        for section in self:
            section.estimated_total = sum(
                section.product_line_ids.mapped("price_subtotal")
            )

    # --------------------------------------------------- convert to roof object
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
    quantity = fields.Float(string="Hoeveelheid", digits="Product Unit of Measure", default=1.0)
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

    @api.onchange("coverage", "product_id")
    def _onchange_coverage(self):
        for line in self:
            target = line.section_id or line.object_id
            if not target:
                continue
            if line.coverage == "surface":
                line.quantity = target.area
            elif line.coverage == "edges":
                line.quantity = target.perimeter
            elif line.coverage == "corners":
                line.quantity = 4.0
            else:  # drainage
                line.quantity = 1.0
