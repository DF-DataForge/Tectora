# -*- coding: utf-8 -*-
"""Werkvoorbereiding: the fields of the paper "Projectinformatie" sheet.

The sheet distinguishes three answers — JA, NEE and "/" (not applicable or
not yet known) — so those questions are three-state selections rather than
booleans: a blank answer must not read as "no".
"""
from odoo import api, fields, models

TRISTATE = [("yes", "Ja"), ("no", "Nee"), ("na", "/")]


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
    checkin_at_work = fields.Selection(
        TRISTATE, string="Checkin@work", default="na",
        help="Verplichte aanwezigheidsregistratie op de werf.",
    )
    asbestos_present = fields.Selection(
        TRISTATE, string="Asbesthoudende materialen", default="na"
    )
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
    material_direct_roof = fields.Selection(
        TRISTATE, string="Materiaal rechtstreeks op het dak", default="na"
    )
    material_through_building = fields.Selection(
        TRISTATE, string="Materiaal moet doorheen het gebouw", default="na"
    )
    material_via_side = fields.Selection(
        TRISTATE, string="Materiaal kan via zijkant van het gebouw", default="na"
    )
    aerial_lift_needed = fields.Selection(
        TRISTATE, string="Hoogwerker nodig", default="na"
    )
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
    transport_over_building = fields.Selection(
        TRISTATE, string="Transport overheen gebouw nodig", default="na"
    )

    # --- extra's te voorzien -------------------------------------------------
    scaffolding_needed = fields.Selection(
        TRISTATE, string="Stelling nodig", default="na"
    )
    mobile_scaffolding_needed = fields.Selection(
        TRISTATE, string="Rolstelling nodig", default="na"
    )
    concrete_drilling_needed = fields.Selection(
        TRISTATE, string="Betonboring nodig", default="na"
    )
    hvac_contractor_needed = fields.Selection(
        TRISTATE, string="Aannemer HVAC nodig", default="na"
    )
    precautions_needed = fields.Selection(
        TRISTATE, string="Specifieke voorzorgsmaatregelen nodig", default="na"
    )
    precautions_note = fields.Text(
        string="Voorzorgsmaatregelen",
        help="bv. PE-folie en schilderskarton (zie offerte).",
    )

    # --- te voorzien ter plaatse --------------------------------------------
    generator_needed = fields.Selection(
        TRISTATE, string="Stroomgenerator nodig", default="na"
    )
    site_toilet_needed = fields.Selection(
        TRISTATE, string="Werftoilet nodig", default="na"
    )
    site_hut_needed = fields.Selection(
        TRISTATE, string="Werfkeet nodig", default="na"
    )

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
    easy_parking = fields.Selection(
        TRISTATE, string="Makkelijk parkeren", default="na"
    )
    parking_ban_needed = fields.Selection(
        TRISTATE, string="Parkeerverbod", default="na"
    )
    driveway_paved = fields.Selection(
        TRISTATE, string="Oprit verhard", default="na"
    )

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
