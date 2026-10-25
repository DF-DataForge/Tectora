# -*- coding: utf-8 -*-
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Two time norms per sold unit, because one works item can carry both: a
    # "leveren en plaatsen" post that first takes the old one down.
    tectora_hours_execution_per_uom = fields.Float(
        string="Uren opbouw per eenheid",
        digits=(16, 3),
        help="Uitvoeringstijd van de opbouwwerken in uren per verkochte eenheid "
        "van dit product (per m², per lm, per stuk); 0,25 is een kwartier. "
        "Elke offertelijn vermenigvuldigt dit met haar hoeveelheid; de som "
        "staat op de offerte en wordt bij bevestiging de toegewezen tijd van "
        "de taak Uitvoeringswerken van het project.",
    )
    tectora_hours_demolition_per_uom = fields.Float(
        string="Uren afbraak per eenheid",
        digits=(16, 3),
        help="Tijd van de afbraakwerken in uren per verkochte eenheid van dit "
        "product. Wordt op dezelfde manier gesommeerd en bij bevestiging de "
        "toegewezen tijd van de taak Afbraakwerken van het project.",
    )

    # Hercalculatie: a component a bill of materials counts in m, m² or m³
    # (per m² of roof, so much m² of insulation) but that is bought and
    # stocked per piece of L, L × B or L × B × H. The material list turns the
    # length, area or volume into pieces.
    tectora_recalc = fields.Boolean(
        string="Hercalculatie",
        help="Op een stuklijst staat de hoeveelheid van dit product in m, m² "
        "of m³ (de reken-UoM); de materiaallijst rekent die om naar stuks met "
        "de afmetingen hieronder, naar boven afgerond. Bv. 10 m² van een "
        "plaat van 1 m × 0,5 m = 20 stuks; 10 m van een profiel van 3 m = 4 "
        "stuks.",
    )
    tectora_recalc_uom = fields.Selection(
        [("m", "m"), ("m2", "m²"), ("m3", "m³")],
        string="Reken-UoM",
        default="m2",
        help="m: één stuk is L (B en H staan er ter info). m²: één stuk is L × B. "
        "m³: één stuk is L × B × H.",
    )
    tectora_length = fields.Float(string="Lengte (L)", digits=(16, 4), help="In meter.")
    tectora_width = fields.Float(string="Breedte (B)", digits=(16, 4), help="In meter.")
    tectora_height = fields.Float(string="Hoogte (H)", digits=(16, 4), help="In meter.")
    # The form takes the dimensions in millimetres; they are kept (and
    # calculated with) in metres.
    tectora_length_mm = fields.Float(
        string="Lengte (L, mm)", digits=(16, 1),
        compute="_compute_tectora_dimensions_mm", inverse="_inverse_tectora_length_mm",
        help="In millimeter.",
    )
    tectora_width_mm = fields.Float(
        string="Breedte (B, mm)", digits=(16, 1),
        compute="_compute_tectora_dimensions_mm", inverse="_inverse_tectora_width_mm",
        help="In millimeter.",
    )
    tectora_height_mm = fields.Float(
        string="Hoogte (H, mm)", digits=(16, 1),
        compute="_compute_tectora_dimensions_mm", inverse="_inverse_tectora_height_mm",
        help="In millimeter.",
    )
    tectora_recalc_size = fields.Float(
        string="Per stuk",
        compute="_compute_tectora_recalc_size",
        digits=(16, 4),
        help="Lengte (m), oppervlakte (m²) of volume (m³) van één stuk.",
    )

    MM_FIELDS = {
        "tectora_length_mm": "tectora_length",
        "tectora_width_mm": "tectora_width",
        "tectora_height_mm": "tectora_height",
    }

    @api.model
    def _tectora_dimensions_in_metres(self, vals):
        """The values with the dimensions in mm turned into the stored
        metres, so the hercalculatie check sees them in the same save."""
        vals = dict(vals)
        for mm_field, field in self.MM_FIELDS.items():
            if mm_field in vals:
                vals[field] = (vals.pop(mm_field) or 0.0) / 1000.0
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._tectora_dimensions_in_metres(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._tectora_dimensions_in_metres(vals))

    @api.depends("tectora_length", "tectora_width", "tectora_height")
    def _compute_tectora_dimensions_mm(self):
        for template in self:
            template.tectora_length_mm = template.tectora_length * 1000.0
            template.tectora_width_mm = template.tectora_width * 1000.0
            template.tectora_height_mm = template.tectora_height * 1000.0

    def _inverse_tectora_length_mm(self):
        for template in self:
            template.tectora_length = template.tectora_length_mm / 1000.0

    def _inverse_tectora_width_mm(self):
        for template in self:
            template.tectora_width = template.tectora_width_mm / 1000.0

    def _inverse_tectora_height_mm(self):
        for template in self:
            template.tectora_height = template.tectora_height_mm / 1000.0

    @api.depends("tectora_recalc_uom", "tectora_length_mm", "tectora_width_mm", "tectora_height_mm")
    def _compute_tectora_recalc_size(self):
        # From the mm fields (which follow the stored metres), so the size
        # per piece follows the form while the dimensions are typed.
        for template in self:
            uom = template.tectora_recalc_uom
            size = template.tectora_length_mm / 1000.0
            if uom in ("m2", "m3"):
                size *= template.tectora_width_mm / 1000.0
            if uom == "m3":
                size *= template.tectora_height_mm / 1000.0
            template.tectora_recalc_size = size

    @api.constrains(
        "tectora_recalc", "tectora_recalc_uom",
        "tectora_length", "tectora_width", "tectora_height",
    )
    def _check_tectora_recalc(self):
        for template in self.filtered("tectora_recalc"):
            if template.tectora_recalc_size <= 0.0:
                raise ValidationError(
                    _(
                        "%(product)s: geef voor de hercalculatie in %(uom)s %(sizes)s "
                        "groter dan 0 in.",
                        product=template.display_name,
                        uom=dict(self._fields["tectora_recalc_uom"].selection).get(
                            template.tectora_recalc_uom, ""
                        ),
                        sizes={
                            "m": _("de lengte"),
                            "m2": _("de lengte en de breedte"),
                        }.get(template.tectora_recalc_uom, _("de lengte, de breedte en de hoogte")),
                    )
                )

    def _tectora_recalculate(self, quantity):
        """Pieces for ``quantity`` m, m² or m³ of this product, rounded up; the
        quantity unchanged when the product has no hercalculatie."""
        self.ensure_one()
        if not self.tectora_recalc or self.tectora_recalc_size <= 0.0:
            return quantity
        pieces = quantity / self.tectora_recalc_size
        # Up to whole pieces, without 20.000000001 becoming 21.
        return float(math.ceil(round(pieces, 6)))

    def _tectora_recalc_explanation(self, quantity, rounded=False):
        """How ``quantity`` in the Reken-UoM becomes pieces, as a line of
        text for a bill of materials: "1,00 m² ÷ 0,72 m² per stuk = 1,39
        stuks". With ``rounded``, the whole pieces the material list takes.
        Empty when the product has no hercalculatie."""
        self.ensure_one()
        size = self.tectora_recalc_size
        if not self.tectora_recalc or size <= 0.0:
            return ""
        unit = dict(self._fields["tectora_recalc_uom"].selection).get(self.tectora_recalc_uom, "")
        exact = quantity / size
        text = _(
            "%(qty)s %(unit)s ÷ %(size)s %(unit)s per stuk = %(pieces)s stuks",
            qty=formatLang(self.env, quantity, digits=2),
            unit=unit,
            size=formatLang(self.env, size, digits=4).rstrip("0").rstrip(",.") or "0",
            pieces=formatLang(self.env, exact, digits=2),
        )
        if rounded:
            text = _("%(text)s → %(whole)s stuks op de materiaallijst", text=text,
                     whole=formatLang(self.env, self._tectora_recalculate(quantity), digits=0))
        return text


# The hercalculatie fields, written on the template in one go: the check
# on them needs the unit and the dimensions of the same save.
RECALC_FIELDS = (
    "tectora_recalc", "tectora_recalc_uom",
    "tectora_length", "tectora_width", "tectora_height",
    "tectora_length_mm", "tectora_width_mm", "tectora_height_mm",
)


class ProductProduct(models.Model):
    """A variant writes the template's fields one by one (they are related
    fields), so switching hercalculatie on would be checked before the unit
    and the dimensions of the same save are there. They go to the template
    together instead."""

    _inherit = "product.product"

    @api.model
    def _tectora_split_recalc_values(self, vals):
        recalc = {key: vals[key] for key in RECALC_FIELDS if key in vals}
        rest = {key: value for key, value in vals.items() if key not in recalc}
        return recalc, rest

    @api.model_create_multi
    def create(self, vals_list):
        split = [self._tectora_split_recalc_values(vals) for vals in vals_list]
        products = super().create([rest for _recalc, rest in split])
        for product, (recalc, _rest) in zip(products, split):
            if recalc:
                product.product_tmpl_id.write(recalc)
        return products

    def write(self, vals):
        recalc, rest = self._tectora_split_recalc_values(vals)
        result = super().write(rest) if rest or not recalc else True
        if recalc:
            self.product_tmpl_id.write(recalc)
        return result
