# -*- coding: utf-8 -*-
"""The roofs (daken) of a roof project.

A project can cover several roofs -- a house and its garage, a main roof and
an annex -- each with its own plan. The drawing widget works on the roof
project's own drawing fields; the roof that is opened on it (``active_roof_id``)
keeps a copy of everything drawn, and opening another roof swaps the drawing
on the project for that roof's. Sections and objects carry their roof, so the
measurement of every roof stays apart while the project totals all of them.
"""
from odoo import _, api, fields, models

DEFAULT_SCALE_M_PER_PX = 0.02

# The fields that make up one roof's plan, on the roof project (the copy the
# drawing widget edits) and on every roof (where it is kept).
DRAWING_FIELDS = (
    "canvas_data",
    "canvas_snapshot",
    "background_image",
    "bg_lat",
    "bg_lng",
    "bg_north",
    "bg_south",
    "bg_east",
    "bg_west",
    "scale_m_per_px",
)


class TectoraRoofProjectRoof(models.Model):
    _name = "tectora.roof.project.roof"
    _description = "Dak van een dakproject"
    _order = "project_id, sequence, id"

    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    sequence = fields.Integer(default=10)
    number = fields.Integer(
        string="Nr.", compute="_compute_number",
        help="Volgnummer van het dak binnen het project.",
    )
    name = fields.Char(string="Dak", required=True)
    description = fields.Text(
        string="Omschrijving",
        help="Wat dit dak is (garage, achterbouw, hoofddak, ...); staat mee in "
        "de subsectie van het dak op de offerte.",
    )
    is_active = fields.Boolean(
        string="Op de tekening", compute="_compute_is_active",
        help="Dit dak staat nu open op de tekening van het dakproject.",
    )

    # --- The plan of this roof ------------------------------------------------
    canvas_data = fields.Text(string="Tekening (JSON)", default='{"shapes": []}')
    canvas_snapshot = fields.Binary(string="Tekening (snapshot)", attachment=True)
    background_image = fields.Image(string="Satellietbeeld", max_width=2560, max_height=2560)
    bg_lat = fields.Float(digits=(16, 7))
    bg_lng = fields.Float(digits=(16, 7))
    bg_north = fields.Float(digits=(16, 7))
    bg_south = fields.Float(digits=(16, 7))
    bg_east = fields.Float(digits=(16, 7))
    bg_west = fields.Float(digits=(16, 7))
    scale_m_per_px = fields.Float(digits=(16, 6), default=DEFAULT_SCALE_M_PER_PX)

    section_ids = fields.One2many("tectora.roof.section", "roof_id", string="Daksecties")
    roof_object_ids = fields.One2many("tectora.roof.object", "roof_id", string="Dakobjecten")
    total_area = fields.Float(
        string="Oppervlakte (m²)", compute="_compute_totals", store=True, digits=(16, 2),
    )
    total_perimeter = fields.Float(
        string="Omtrek (m)", compute="_compute_totals", store=True, digits=(16, 2),
    )

    @api.depends("project_id.roof_ids", "sequence")
    def _compute_number(self):
        for roof in self:
            roofs = roof.project_id.roof_ids.sorted(lambda r: (r.sequence, r.id or 0))
            roof.number = (list(roofs).index(roof) + 1) if roof in roofs else 0

    @api.depends("project_id.active_roof_id")
    def _compute_is_active(self):
        for roof in self:
            roof.is_active = roof.project_id.active_roof_id == roof

    @api.depends("section_ids.area", "section_ids.perimeter")
    def _compute_totals(self):
        for roof in self:
            roof.total_area = sum(roof.section_ids.mapped("area"))
            roof.total_perimeter = sum(roof.section_ids.mapped("perimeter"))

    def _subsection_name(self):
        """The title of this roof's subsection on the quotation."""
        self.ensure_one()
        name = self.name or _("Dak %s", self.number)
        description = (self.description or "").strip()
        if description:
            return "%s – %s" % (name, description)
        return name

    # ------------------------------------------------------------ lifecycle
    @api.model_create_multi
    def create(self, vals_list):
        Project = self.env["tectora.roof.project"]
        for vals in vals_list:
            if not vals.get("name") and vals.get("project_id"):
                count = len(Project.browse(vals["project_id"]).roof_ids)
                vals["name"] = _("Dak %s", count + 1)
        roofs = super().create(vals_list)
        for project in roofs.project_id:
            new = roofs.filtered(lambda roof: roof.project_id == project)
            if not project.active_roof_id:
                # The project's first roof takes over what is drawn so far:
                # the drawing and the sections and objects made from it.
                first = new[:1]
                first.with_context(tectora_roof_switch=True).write(
                    project._tectora_drawing_values()
                )
                project.section_ids.filtered(lambda s: not s.roof_id).write(
                    {"roof_id": first.id}
                )
                project.roof_object_ids.filtered(lambda o: not o.roof_id).write(
                    {"roof_id": first.id}
                )
                project.with_context(tectora_roof_switch=True).write(
                    {"active_roof_id": first.id}
                )
            # A new roof inherits the satellite image of the site, so its plan
            # starts on the same photo; the drawing itself starts empty.
            source = project.active_roof_id
            for roof in new.filtered(lambda r: r != source and not r.background_image):
                roof.with_context(tectora_roof_switch=True).write({
                    name: source[name]
                    for name in DRAWING_FIELDS
                    if name not in ("canvas_data", "canvas_snapshot")
                })
        return roofs

    def write(self, vals):
        result = super().write(vals)
        if {"name", "description", "sequence"} & set(vals):
            self._tectora_rename_subsections()
        return result

    def unlink(self):
        for roof in self:
            project = roof.project_id
            if project.active_roof_id == roof:
                others = project.roof_ids - self
                if others:
                    project._tectora_open_roof(others[:1], save_current=False)
                else:
                    project.with_context(tectora_roof_switch=True).write(
                        {"active_roof_id": False}
                    )
        # Only on a quotation that follows the measurement; otherwise its
        # lines stay, as the user made them.
        lines = self.env["sale.order.line"].search([
            ("tectora_roof_id", "in", self.ids),
            ("order_id.state", "in", ("draft", "sent")),
            ("order_id.tectora_follow_measurement", "=", True),
        ])
        if lines:
            lines.unlink()
        return super().unlink()

    def _tectora_rename_subsections(self):
        """The subsections of these roofs on open quotations follow their
        name and description."""
        lines = self.env["sale.order.line"].search([
            ("tectora_roof_id", "in", self.ids),
            ("display_type", "=", "line_subsection"),
            ("order_id.state", "in", ("draft", "sent")),
        ])
        for line in lines:
            name = line.tectora_roof_id._subsection_name()
            if line.name != name:
                line.with_context(tectora_sync=True).write({"name": name})

    # -------------------------------------------------------------- buttons
    def action_open_plan(self):
        """Put this roof's plan on the drawing of the roof project."""
        self.ensure_one()
        project = self.project_id
        if project.active_roof_id != self:
            project._tectora_open_roof(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": project.id,
            "view_mode": "form",
            "target": "current",
            "context": {"tectora_open_drawing": True},
        }
