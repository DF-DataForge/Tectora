# -*- coding: utf-8 -*-
"""Werkvoorbereiding: the fields of the paper "Projectinformatie" sheet (the
Werf tab). The yes/no questions of the sheet are checkboxes: ticked is "Ja",
unticked "Nee".
"""
from odoo import api, fields, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    # --- kop van het blad ----------------------------------------------------
    date_deadline = fields.Date(string="Deadline", tracking=True)
    project_manager_id = fields.Many2one(
        "res.users", string="Projectleider", tracking=True
    )
    project_manager_email = fields.Char(related="project_manager_id.email")
    project_manager_phone = fields.Char(related="project_manager_id.phone")
    site_contact_id = fields.Many2one(
        "res.partner",
        string="Contactpersoon werf",
        help="Contact ter plaatse; laat leeg als dit de klant zelf is.",
    )
    site_contact_phone = fields.Char(related="site_contact_id.phone")
    site_contact_email = fields.Char(related="site_contact_id.email")

    # --- voorbereiding -------------------------------------------------------
    checkin_at_work = fields.Boolean(
        string="Checkin@work",
        help="Verplichte aanwezigheidsregistratie op de werf.",
    )
    asbestos_present = fields.Boolean(string="Asbesthoudende materialen")
    roof_height = fields.Float(string="Hoogte dak(en) (m)", digits=(16, 2))
    roof_substrate = fields.Selection(
        [
            ("hout", "Hout"),
            ("beton", "Beton"),
            ("steeldeck", "Steeldeck"),
            ("isolatie", "Isolatie"),
            ("roofing", "Bestaande roofing"),
            ("andere", "Andere"),
        ],
        string="Ondergrond dak(en)",
    )
    roof_substrate_note = fields.Char(string="Ondergrond (toelichting)")

    # --- bereikbaarheid materiaal -------------------------------------------
    material_direct_roof = fields.Boolean(string="Materiaal rechtstreeks op het dak")
    material_through_building = fields.Boolean(string="Materiaal moet doorheen het gebouw")
    material_via_side = fields.Boolean(string="Materiaal kan via zijkant van het gebouw")
    aerial_lift_needed = fields.Boolean(string="Hoogwerker nodig")
    aerial_lift_type = fields.Char(string="Hoogwerker (type)")

    # --- transport -----------------------------------------------------------
    material_transport = fields.Char(
        string="Transport materialen naar werf",
        help="bv. de leverancier (Modde) of eigen transport.",
    )
    waste_disposal = fields.Char(string="Afval afvoer via")
    supplier_pickup_time = fields.Char(
        string="Geschat uur levering/ophaling leverancier",
        help="Geschat uur voor levering/ophaling door de leverancier, indien "
        "het afval mee teruggaat.",
    )
    transport_over_building = fields.Boolean(string="Transport overheen gebouw nodig")

    # --- extra's te voorzien -------------------------------------------------
    scaffolding_needed = fields.Boolean(string="Stelling nodig")
    mobile_scaffolding_needed = fields.Boolean(string="Rolstelling nodig")
    concrete_drilling_needed = fields.Boolean(string="Betonboring nodig")
    hvac_contractor_needed = fields.Boolean(string="Aannemer HVAC nodig")
    precautions_needed = fields.Boolean(string="Specifieke voorzorgsmaatregelen nodig")
    precautions_note = fields.Text(
        string="Voorzorgsmaatregelen",
        help="bv. PE-folie en schilderskarton (zie offerte).",
    )

    # --- te voorzien ter plaatse --------------------------------------------
    generator_needed = fields.Boolean(string="Stroomgenerator nodig")
    site_toilet_needed = fields.Boolean(string="Werftoilet nodig")
    site_hut_needed = fields.Boolean(string="Werfkeet nodig")

    # --- EPDM ----------------------------------------------------------------
    epdm_thickness = fields.Float(
        string="EPDM dikte (mm)", digits=(16, 2),
        help="Dikte van de EPDM-doeken, bv. 1,10 mm.",
    )
    epdm_sheet_ids = fields.One2many(
        "tectora.roof.epdm.sheet", "project_id", string="EPDM-doeken"
    )
    epdm_sheet_count = fields.Integer(compute="_compute_epdm_totals")
    epdm_total_area = fields.Float(
        string="EPDM totaal (m²)", compute="_compute_epdm_totals", digits=(16, 2)
    )

    # --- afwijking dakranden ------------------------------------------------
    roof_edge_types = fields.Char(string="Type(s) dakranden")
    roof_edge_colors = fields.Char(string="Kleur(en) dakranden")

    # --- bereikbaarheid werf -------------------------------------------------
    easy_parking = fields.Boolean(string="Makkelijk parkeren")
    parking_ban_needed = fields.Boolean(string="Parkeerverbod")
    driveway_paved = fields.Boolean(string="Oprit verhard")

    # --- andere werken -------------------------------------------------------
    other_works = fields.Text(
        string="Andere werken / extra's",
        help="bv. zonnepanelen weg en terug: partner.",
    )

    @api.depends("epdm_sheet_ids.area")
    def _compute_epdm_totals(self):
        for project in self:
            project.epdm_sheet_count = len(project.epdm_sheet_ids)
            project.epdm_total_area = sum(project.epdm_sheet_ids.mapped("area"))

    def _info_sheet_sections(self):
        """The site sheet as two columns of cards, each a title and rows of
        (label, kind, value): kind "bool" renders as a Ja/Nee mark, "text" as
        it is. Keeps the printed sheet's structure in one place."""
        self.ensure_one()

        def flag(field_name):
            return ("bool", bool(self[field_name]))

        def text(value):
            return ("text", value or "/")

        substrate = self._info_label("roof_substrate") if self.roof_substrate else ""
        if self.roof_substrate_note:
            substrate = "%s (%s)" % (substrate or "Andere", self.roof_substrate_note)
        lift = ("Ja — %s" % self.aerial_lift_type) if self.aerial_lift_needed and self.aerial_lift_type else None

        left = [
            ("Voorbereiding", [
                ("Checkin@work", *flag("checkin_at_work")),
                ("Asbesthoudende materialen", *flag("asbestos_present")),
                ("Hoogte dak(en)", *text("%.2f m" % self.roof_height if self.roof_height else "")),
                ("Ondergrond dak(en)", *text(substrate)),
            ]),
            ("Bereikbaarheid materiaal", [
                ("Materiaal rechtstreeks op het dak", *flag("material_direct_roof")),
                ("Materiaal doorheen het gebouw", *flag("material_through_building")),
                ("Materiaal via zijkant gebouw", *flag("material_via_side")),
                ("Hoogwerker nodig", *(text(lift) if lift else flag("aerial_lift_needed"))),
            ]),
            ("Transport", [
                ("Transport materialen naar werf", *text(self.material_transport)),
                ("Afval afvoer via", *text(self.waste_disposal)),
                ("Geschat uur levering / ophaling", *text(self.supplier_pickup_time)),
                ("Transport overheen gebouw", *flag("transport_over_building")),
            ]),
            ("Bereikbaarheid werf", [
                ("Makkelijk parkeren", *flag("easy_parking")),
                ("Parkeerverbod nodig", *flag("parking_ban_needed")),
                ("Oprit verhard", *flag("driveway_paved")),
            ]),
        ]
        extras = [
            ("Stelling", *flag("scaffolding_needed")),
            ("Rolstelling", *flag("mobile_scaffolding_needed")),
            ("Betonboring", *flag("concrete_drilling_needed")),
            ("Aannemer HVAC", *flag("hvac_contractor_needed")),
            ("Specifieke voorzorgsmaatregelen", *flag("precautions_needed")),
        ]
        if self.precautions_note:
            extras.append(("Voorzorgsmaatregelen", "note", self.precautions_note))
        right = [
            ("Extra's te voorzien", extras),
            ("Te voorzien ter plaatse", [
                ("Stroomgenerator", *flag("generator_needed")),
                ("Werftoilet", *flag("site_toilet_needed")),
                ("Werfkeet", *flag("site_hut_needed")),
            ]),
            ("Afwijking dakranden", [
                ("Type(s)", *text(self.roof_edge_types)),
                ("Kleur(en)", *text(self.roof_edge_colors)),
            ]),
        ]
        return left, right

    def _info_label(self, field_name):
        """Human label of a field's value, for the printed sheet."""
        self.ensure_one()
        value = self[field_name]
        field = self._fields[field_name]
        if field.type == "selection" and value:
            return dict(field._description_selection(self.env)).get(value, value)
        if field.type == "boolean":
            return _tick(value)
        return value or "/"


def _tick(value):
    return "Ja" if value else "Nee"
