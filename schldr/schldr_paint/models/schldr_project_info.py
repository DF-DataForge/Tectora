# -*- coding: utf-8 -*-
"""Werkvoorbereiding: the fields of the site sheet (the Werf tab). The yes/no
questions of the sheet are checkboxes: ticked is "Ja", unticked "Nee".
"""
from odoo import fields, models

from .schldr_system import GROUP_LABELS, MEASURES

MEASURE_UNITS = {"m2": "m²", "m": "m", "piece": "st"}
assert set(MEASURE_UNITS) == {key for key, _label in MEASURES}


class SchldrProject(models.Model):
    _inherit = "schldr.project"

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
    lead_paint_present = fields.Boolean(
        string="Loodhoudende verf",
        help="Oude verflagen met lood: schuren enkel met afzuiging en bescherming.",
    )
    substrate = fields.Selection(
        [
            ("pleister", "Nieuw pleisterwerk"),
            ("gipsplaat", "Gipsplaat"),
            ("schilderwerk", "Bestaand schilderwerk"),
            ("behang", "Behang"),
            ("hout", "Hout"),
            ("andere", "Andere"),
        ],
        string="Ondergrond",
    )
    substrate_note = fields.Char(string="Ondergrond (toelichting)")
    wallpaper_removal = fields.Boolean(string="Behang verwijderen")
    repairs_needed = fields.Boolean(string="Herstellingen en plamuurwerk")

    # --- de woning tijdens de werken ----------------------------------------
    occupied = fields.Boolean(string="Bewoond tijdens de werken")
    furniture_by = fields.Selection(
        [
            ("klant", "Door de klant"),
            ("wij", "Door ons"),
            ("geen", "Geen meubels"),
        ],
        string="Meubels verplaatsen",
    )
    floor_protection = fields.Boolean(string="Vloeren afdekken", default=True)
    water_available = fields.Boolean(string="Water ter plaatse", default=True)
    power_available = fields.Boolean(string="Stroom ter plaatse", default=True)

    # --- bereikbaarheid werf -------------------------------------------------
    easy_parking = fields.Boolean(string="Makkelijk parkeren")
    parking_ban_needed = fields.Boolean(string="Parkeerverbod")
    floor_access = fields.Char(
        string="Verdieping en lift", help="bv. 3de verdieping, lift aanwezig."
    )
    key_arrangement = fields.Char(
        string="Sleutel en toegang", help="bv. sleutel bij de buren op nr. 12."
    )

    # --- materiaal en afval --------------------------------------------------
    material_transport = fields.Char(
        string="Materiaal naar de werf",
        help="bv. geleverd door de groothandel of eigen transport.",
    )
    waste_disposal = fields.Char(string="Afval afvoer via")

    # --- extra's te voorzien -------------------------------------------------
    scaffolding_needed = fields.Boolean(string="Stelling nodig")
    mobile_scaffolding_needed = fields.Boolean(string="Rolstelling nodig")
    aerial_lift_needed = fields.Boolean(string="Hoogwerker nodig")
    aerial_lift_type = fields.Char(string="Hoogwerker (type)")
    precautions_needed = fields.Boolean(string="Specifieke voorzorgsmaatregelen nodig")
    precautions_note = fields.Text(
        string="Voorzorgsmaatregelen",
        help="bv. stofschot aan de trap, parket volledig afdekken.",
    )

    site_photo_facade = fields.Image(string="Gevel", max_width=1600, max_height=1600)
    site_photo_interior = fields.Image(string="Interieur", max_width=1600, max_height=1600)

    # --- andere werken -------------------------------------------------------
    other_works = fields.Text(
        string="Andere werken / extra's",
        help="bv. gordijnrails weg en terug door de klant.",
    )

    def _info_sheet_sections(self):
        """The site sheet as two columns of cards, each a title and rows of
        (label, kind, value): kind "bool" renders as a Ja/Nee mark, "text" as
        it is. Keeps the printed sheet's structure in one place."""
        self.ensure_one()

        def flag(field_name):
            return ("bool", bool(self[field_name]))

        def text(value):
            return ("text", value or "/")

        substrate = self._info_label("substrate") if self.substrate else ""
        if self.substrate_note:
            substrate = "%s (%s)" % (substrate or "Andere", self.substrate_note)
        lift = ("Ja — %s" % self.aerial_lift_type) if self.aerial_lift_needed and self.aerial_lift_type else None

        left = [
            ("Voorbereiding", [
                ("Checkin@work", *flag("checkin_at_work")),
                ("Asbesthoudende materialen", *flag("asbestos_present")),
                ("Loodhoudende verf", *flag("lead_paint_present")),
                ("Ondergrond", *text(substrate)),
                ("Behang verwijderen", *flag("wallpaper_removal")),
                ("Herstellingen en plamuurwerk", *flag("repairs_needed")),
            ]),
            ("De woning tijdens de werken", [
                ("Bewoond", *flag("occupied")),
                ("Meubels verplaatsen", *text(self._info_label("furniture_by") if self.furniture_by else "")),
                ("Vloeren afdekken", *flag("floor_protection")),
                ("Water ter plaatse", *flag("water_available")),
                ("Stroom ter plaatse", *flag("power_available")),
            ]),
            ("Bereikbaarheid werf", [
                ("Makkelijk parkeren", *flag("easy_parking")),
                ("Parkeerverbod nodig", *flag("parking_ban_needed")),
                ("Verdieping en lift", *text(self.floor_access)),
                ("Sleutel en toegang", *text(self.key_arrangement)),
            ]),
        ]
        extras = [
            ("Stelling", *flag("scaffolding_needed")),
            ("Rolstelling", *flag("mobile_scaffolding_needed")),
            ("Hoogwerker", *(text(lift) if lift else flag("aerial_lift_needed"))),
            ("Specifieke voorzorgsmaatregelen", *flag("precautions_needed")),
        ]
        if self.precautions_note:
            extras.append(("Voorzorgsmaatregelen", "note", self.precautions_note))
        right = [
            ("Extra's te voorzien", extras),
            ("Materiaal en afval", [
                ("Materiaal naar de werf", *text(self.material_transport)),
                ("Afval afvoer via", *text(self.waste_disposal)),
            ]),
        ]
        return left, right

    def _schldr_colour_schedule(self):
        """What is painted where, for the site sheet and the crew: per room
        its surface groups with the paint system, the colour and how much.

        [{"room": "Woonkamer", "rows": [{"group": "Muren", "system": ...,
          "colour": ..., "hex": ..., "quantity": 46.8, "unit": "m²"}]}]
        """
        self.ensure_one()
        order = [group for group, _label in GROUP_LABELS]
        labels = dict(GROUP_LABELS)
        schedule = []
        for room in self.room_ids:
            totals = {}
            for assignment in self.assignment_ids.filtered(lambda a: a.room_id == room):
                key = (assignment.group, assignment.system_id, assignment.colour_id)
                totals[key] = totals.get(key, 0.0) + assignment.quantity
            if not totals:
                continue
            rows = []
            for (group, system, colour), quantity in sorted(
                totals.items(),
                key=lambda item: (order.index(item[0][0]), item[0][1].sequence, item[0][1].id, item[0][2].id),
            ):
                rows.append({
                    "group": labels[group],
                    "system": system.name,
                    "colour": colour.display_name or "",
                    "hex": colour.hex or "",
                    "quantity": round(quantity, 2),
                    "unit": MEASURE_UNITS[system.sale_measure],
                })
            schedule.append({"room": room._schldr_title(), "rows": rows})
        return schedule

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
