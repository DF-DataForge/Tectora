# -*- coding: utf-8 -*-
"""The plan of a painting project as records: levels, rooms, their surfaces
and what is put on them. All of it is a mirror of the plan document
(schldr.project.canvas_data), rebuilt by action_sync_from_canvas and matched
on ``canvas_ref``, so lists, reports and the order can read it; nobody edits
these by hand."""
from odoo import api, fields, models

from ..lib import measure
from .schldr_system import GROUP_LABELS

SURFACE_KINDS = [
    ("wall", "Muur"),
    ("ceiling", "Plafond"),
    ("slope", "Schuin plafond"),
    ("floor", "Vloer"),
    ("skirting", "Plinten"),
    ("moulding", "Kroonlijst"),
    ("frame", "Omlijsting"),
    ("door_leaf", "Deurblad"),
    ("radiator", "Radiator"),
    ("custom", "Vrij element"),
]


class SchldrLevel(models.Model):
    _name = "schldr.level"
    _description = "Verdieping"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "schldr.project", required=True, ondelete="cascade", index=True
    )
    canvas_ref = fields.Char(index=True)
    name = fields.Char(string="Verdieping", required=True)
    sequence = fields.Integer(default=10)
    room_ids = fields.One2many("schldr.room", "level_id", string="Ruimtes")


class SchldrRoom(models.Model):
    _name = "schldr.room"
    _description = "Ruimte"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "schldr.project", required=True, ondelete="cascade", index=True
    )
    level_id = fields.Many2one("schldr.level", string="Verdieping", ondelete="cascade")
    canvas_ref = fields.Char(index=True)
    name = fields.Char(string="Ruimte", required=True)
    sequence = fields.Integer(default=10)
    height = fields.Float(string="Plafondhoogte (m)", digits=(16, 2))
    floor_area = fields.Float(string="Vloeroppervlakte (m²)", digits=(16, 2))
    perimeter = fields.Float(string="Omtrek (m)", digits=(16, 2))
    wall_area = fields.Float(string="Muren (m²)", digits=(16, 2))
    ceiling_area = fields.Float(string="Plafond (m²)", digits=(16, 2))
    surface_ids = fields.One2many("schldr.surface", "room_id", string="Oppervlakken")

    def _schldr_title(self):
        """"Verdieping 1 – Slaapkamer" when the project has several levels."""
        self.ensure_one()
        if len(self.project_id.level_ids) > 1 and self.level_id:
            return "%s – %s" % (self.level_id.name, self.name)
        return self.name


class SchldrSurface(models.Model):
    _name = "schldr.surface"
    _description = "Te schilderen oppervlak"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "schldr.project", required=True, ondelete="cascade", index=True
    )
    room_id = fields.Many2one(
        "schldr.room", string="Ruimte", required=True, ondelete="cascade", index=True
    )
    level_id = fields.Many2one(related="room_id.level_id", store=True)
    canvas_ref = fields.Char(index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Oppervlak", required=True)
    kind = fields.Selection(SURFACE_KINDS, string="Soort", required=True)
    group = fields.Selection(GROUP_LABELS, string="Groep", required=True, index=True)
    area_gross = fields.Float(string="Bruto (m²)", digits=(16, 2))
    area_openings = fields.Float(string="Openingen (m²)", digits=(16, 2))
    area_reveals = fields.Float(string="Dagkanten (m²)", digits=(16, 2))
    area_net = fields.Float(string="Netto (m²)", digits=(16, 2))
    area_billed = fields.Float(
        string="Aangerekend (m²)", digits=(16, 2),
        help="De oppervlakte op de offerte: kleine openingen worden niet "
        "afgetrokken als het bedrijf dat zo ingesteld heeft.",
    )
    length = fields.Float(string="Lengte (m)", digits=(16, 2))
    count = fields.Integer(string="Aantal")
    paint_area = fields.Float(
        string="Te dekken (m²)", digits=(16, 2),
        help="De oppervlakte waarvoor verf nodig is.",
    )
    height_max = fields.Float(string="Hoogste punt (m)", digits=(16, 2))
    assignment_ids = fields.One2many(
        "schldr.assignment", "surface_id", string="Verfsystemen"
    )

    def _schldr_sizes(self):
        """The surface in the shape lib.measure reads."""
        self.ensure_one()
        return {
            "ref": self.canvas_ref,
            "kind": self.kind,
            "group": self.group,
            "area_net": self.area_net,
            "area_billed": self.area_billed,
            "length": self.length,
            "count": self.count,
            "paint_area": self.paint_area,
        }


class SchldrAssignment(models.Model):
    _name = "schldr.assignment"
    _description = "Verfsysteem op een oppervlak"
    _order = "project_id, surface_id, sequence, id"

    surface_id = fields.Many2one(
        "schldr.surface", required=True, ondelete="cascade", index=True
    )
    project_id = fields.Many2one(related="surface_id.project_id", store=True, index=True)
    room_id = fields.Many2one(related="surface_id.room_id", store=True)
    group = fields.Selection(related="surface_id.group", store=True)
    sequence = fields.Integer(default=10)
    system_id = fields.Many2one(
        "schldr.paint.system", string="Verfsysteem", required=True, ondelete="restrict"
    )
    colour_id = fields.Many2one("schldr.colour", string="Kleur", ondelete="restrict")
    quantity = fields.Float(
        string="Hoeveelheid",
        compute="_compute_quantity",
        store=True,
        digits=(16, 2),
        help="Het oppervlak in de eenheid waarin het systeem verkocht wordt.",
    )

    @api.depends(
        "system_id.sale_measure", "surface_id.area_billed", "surface_id.area_net",
        "surface_id.length", "surface_id.count", "surface_id.paint_area", "surface_id.kind",
    )
    def _compute_quantity(self):
        for assignment in self:
            if not assignment.surface_id or not assignment.system_id:
                assignment.quantity = 0.0
                continue
            assignment.quantity = measure.quantity(
                assignment.surface_id._schldr_sizes(), assignment.system_id.sale_measure
            )


class SchldrProjectLine(models.Model):
    """General works of a painting project: what is not on the plan (covering
    floors, moving furniture, travel) but belongs on the quotation."""

    _name = "schldr.project.line"
    _description = "Algemene werken van een schilderproject"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "schldr.project", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product", string="Product", required=True,
        domain="[('sale_ok', '=', True)]",
    )
    basis = fields.Selection(
        [
            ("fixed", "Vast aantal"),
            ("room", "Per ruimte"),
            ("floor", "Per m² vloer"),
        ],
        string="Telt",
        required=True,
        default="fixed",
        help="Per ruimte en per m² vloer volgen het plan: de hoeveelheid is "
        "het aantal hieronder maal het aantal ruimtes of de vloeroppervlakte.",
    )
    factor = fields.Float(string="Aantal", default=1.0, digits=(16, 2))
    quantity = fields.Float(
        string="Hoeveelheid", compute="_compute_quantity", store=True, digits=(16, 2)
    )
    currency_id = fields.Many2one(related="project_id.currency_id")
    price_subtotal = fields.Monetary(
        string="Geschat", compute="_compute_price_subtotal", currency_field="currency_id"
    )
    sale_line_ids = fields.One2many("sale.order.line", "schldr_line_id")

    @api.depends("basis", "factor", "project_id.room_count", "project_id.total_floor_area")
    def _compute_quantity(self):
        for line in self:
            if line.basis == "room":
                line.quantity = line.factor * line.project_id.room_count
            elif line.basis == "floor":
                line.quantity = line.factor * line.project_id.total_floor_area
            else:
                line.quantity = line.factor

    @api.depends("quantity", "product_id.lst_price")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.product_id.lst_price
