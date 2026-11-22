# -*- coding: utf-8 -*-
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Two time norms per sold unit, because one works item can carry both: a
    # "leveren en plaatsen" post that first takes the old one down.
    schldr_hours_execution_per_uom = fields.Float(
        string="Uren schilderen per eenheid",
        digits=(16, 3),
        help="Tijd van het schilderwerk in uren per verkochte eenheid "
        "van dit product (per m², per lm, per stuk); 0,25 is een kwartier. "
        "Elke offertelijn vermenigvuldigt dit met haar hoeveelheid; de som "
        "staat op de offerte en wordt bij bevestiging de toegewezen tijd van "
        "de taak Schilderwerken van het project. Hoort het product bij een "
        "verfsysteem, dan komt dit uit de lagen van dat systeem.",
    )
    schldr_hours_preparation_per_uom = fields.Float(
        string="Uren voorbereiding per eenheid",
        digits=(16, 3),
        help="Tijd van de voorbereiding (schuren, plamuren, afplakken) in uren per "
        "verkochte eenheid van dit "
        "product. Wordt op dezelfde manier gesommeerd en bij bevestiging de "
        "toegewezen tijd van de taak Voorbereiding van het project.",
    )

    schldr_pack_size_ids = fields.One2many(
        "schldr.pack.size", "product_tmpl_id", string="Verpakkingen",
        help="De potten waarin dit product bestaat (1 L, 2,5 L, 10 L). De "
        "materiaallijst rondt de berekende hoeveelheid af naar de beste "
        "combinatie.",
    )

    # Hercalculatie: a component a bill of materials counts in m, m² or m³
    # (per m² of wall, so much m² of lining) but that is bought and
    # stocked per piece of L, L × B or L × B × H. The material list turns the
    # length, area or volume into pieces.
    schldr_recalc = fields.Boolean(
        string="Hercalculatie",
        help="Op een stuklijst staat de hoeveelheid van dit product in m, m² "
        "of m³ (de reken-UoM); de materiaallijst rekent die om naar stuks met "
        "de afmetingen hieronder, naar boven afgerond. Bv. 10 m² van een "
        "plaat van 1 m × 0,5 m = 20 stuks; 10 m van een profiel van 3 m = 4 "
        "stuks.",
    )
    schldr_recalc_uom = fields.Selection(
        [("m", "m"), ("m2", "m²"), ("m3", "m³")],
        string="Reken-UoM",
        default="m2",
        help="m: één stuk is L (B en H staan er ter info). m²: één stuk is L × B. "
        "m³: één stuk is L × B × H.",
    )
    schldr_length = fields.Float(string="Lengte (L)", digits=(16, 4), help="In meter.")
    schldr_width = fields.Float(string="Breedte (B)", digits=(16, 4), help="In meter.")
    schldr_height = fields.Float(string="Hoogte (H)", digits=(16, 4), help="In meter.")
    # The form takes the dimensions in millimetres; they are kept (and
    # calculated with) in metres.
    schldr_length_mm = fields.Float(
        string="Lengte (L, mm)", digits=(16, 1),
        compute="_compute_schldr_dimensions_mm", inverse="_inverse_schldr_length_mm",
        help="In millimeter.",
    )
    schldr_width_mm = fields.Float(
        string="Breedte (B, mm)", digits=(16, 1),
        compute="_compute_schldr_dimensions_mm", inverse="_inverse_schldr_width_mm",
        help="In millimeter.",
    )
    schldr_height_mm = fields.Float(
        string="Hoogte (H, mm)", digits=(16, 1),
        compute="_compute_schldr_dimensions_mm", inverse="_inverse_schldr_height_mm",
        help="In millimeter.",
    )
    schldr_recalc_margin = fields.Float(
        string="Veiligheidsmarge (%)",
        digits=(16, 2),
        help="Extra materiaal bovenop de berekende hoeveelheid, voor overlap, "
        "snijverlies en breuk: 1 m met 5 % veiligheidsmarge is 1,05 m. De "
        "materiaallijst rekent ermee en de kostprijs op een stuklijst op maat "
        "ook.",
    )
    schldr_recalc_size = fields.Float(
        string="Per stuk",
        compute="_compute_schldr_recalc_size",
        digits=(16, 4),
        help="Lengte (m), oppervlakte (m²) of volume (m³) van één stuk.",
    )

    MM_FIELDS = {
        "schldr_length_mm": "schldr_length",
        "schldr_width_mm": "schldr_width",
        "schldr_height_mm": "schldr_height",
    }

    @api.model
    def _schldr_dimensions_in_metres(self, vals):
        """The values with the dimensions in mm turned into the stored
        metres, so the hercalculatie check sees them in the same save."""
        vals = dict(vals)
        for mm_field, field in self.MM_FIELDS.items():
            if mm_field in vals:
                vals[field] = (vals.pop(mm_field) or 0.0) / 1000.0
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._schldr_dimensions_in_metres(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._schldr_dimensions_in_metres(vals))

    @api.depends("schldr_length", "schldr_width", "schldr_height")
    def _compute_schldr_dimensions_mm(self):
        for template in self:
            template.schldr_length_mm = template.schldr_length * 1000.0
            template.schldr_width_mm = template.schldr_width * 1000.0
            template.schldr_height_mm = template.schldr_height * 1000.0

    def _inverse_schldr_length_mm(self):
        for template in self:
            template.schldr_length = template.schldr_length_mm / 1000.0

    def _inverse_schldr_width_mm(self):
        for template in self:
            template.schldr_width = template.schldr_width_mm / 1000.0

    def _inverse_schldr_height_mm(self):
        for template in self:
            template.schldr_height = template.schldr_height_mm / 1000.0

    @api.depends("schldr_recalc_uom", "schldr_length_mm", "schldr_width_mm", "schldr_height_mm")
    def _compute_schldr_recalc_size(self):
        # From the mm fields (which follow the stored metres), so the size
        # per piece follows the form while the dimensions are typed.
        for template in self:
            uom = template.schldr_recalc_uom
            size = template.schldr_length_mm / 1000.0
            if uom in ("m2", "m3"):
                size *= template.schldr_width_mm / 1000.0
            if uom == "m3":
                size *= template.schldr_height_mm / 1000.0
            template.schldr_recalc_size = size

    @api.constrains(
        "schldr_recalc", "schldr_recalc_uom",
        "schldr_length", "schldr_width", "schldr_height",
    )
    def _check_schldr_recalc(self):
        for template in self.filtered("schldr_recalc"):
            if template.schldr_recalc_size <= 0.0:
                raise ValidationError(
                    _(
                        "%(product)s: geef voor de hercalculatie in %(uom)s %(sizes)s "
                        "groter dan 0 in.",
                        product=template.display_name,
                        uom=dict(self._fields["schldr_recalc_uom"].selection).get(
                            template.schldr_recalc_uom, ""
                        ),
                        sizes={
                            "m": _("de lengte"),
                            "m2": _("de lengte en de breedte"),
                        }.get(template.schldr_recalc_uom, _("de lengte, de breedte en de hoogte")),
                    )
                )

    @api.constrains("schldr_recalc_margin")
    def _check_schldr_recalc_margin(self):
        for template in self:
            if template.schldr_recalc_margin < 0.0:
                raise ValidationError(
                    _("%s: de veiligheidsmarge kan niet negatief zijn.", template.display_name)
                )

    def _schldr_recalc_uom_record(self):
        """The unit of measure of the Reken-UoM (m, m² or m³): the unit a
        bill of materials counts this product in. Empty without
        hercalculatie or without product."""
        if not self:
            return self.env["uom.uom"]
        self.ensure_one()
        if not self.schldr_recalc:
            return self.env["uom.uom"]
        xmlid = {
            "m": "uom.product_uom_meter",
            "m2": "uom.product_uom_square_meter",
            "m3": "uom.product_uom_cubic_meter",
        }.get(self.schldr_recalc_uom)
        return xmlid and self.env.ref(xmlid, raise_if_not_found=False) or self.env["uom.uom"]

    def _schldr_recalc_factor(self, margin=None):
        """1 plus the safety margin: 1,05 for 5 %. ``margin`` (in %) instead
        of the product's, for a line with a margin of its own."""
        self.ensure_one()
        if margin is None:
            margin = self.schldr_recalc_margin
        return 1.0 + (margin or 0.0) / 100.0

    def _schldr_recalc_pieces(self, quantity, margin=None):
        """Pieces, not rounded, for ``quantity`` m, m² or m³ of this product,
        the safety margin included; the quantity unchanged when the product
        has no hercalculatie."""
        self.ensure_one()
        if not self.schldr_recalc or self.schldr_recalc_size <= 0.0:
            return quantity
        return quantity * self._schldr_recalc_factor(margin) / self.schldr_recalc_size

    def _schldr_recalculate(self, quantity, margin=None):
        """Pieces for ``quantity`` m, m² or m³ of this product, the safety
        margin included, rounded up; the quantity unchanged when the product
        has no hercalculatie."""
        self.ensure_one()
        if not self.schldr_recalc or self.schldr_recalc_size <= 0.0:
            return quantity
        return self._schldr_round_pieces(self._schldr_recalc_pieces(quantity, margin))

    @api.model
    def _schldr_round_pieces(self, pieces):
        """Up to whole pieces, without 20.000000001 becoming 21."""
        return float(math.ceil(round(pieces, 6)))

    def _schldr_recalc_explanation(self, quantity, rounded=False, margin=None):
        """How ``quantity`` in the Reken-UoM becomes pieces, as a line of
        text for a bill of materials: "1,00 m² ÷ 0,72 m² per stuk = 1,39
        stuks", with a safety margin "1,00 m + 5 % = 1,05 m ÷ 30 m per stuk
        = 0,04 stuks". With ``rounded``, the whole pieces the material list
        takes. Empty when the product has no hercalculatie."""
        self.ensure_one()
        size = self.schldr_recalc_size
        if not self.schldr_recalc or size <= 0.0:
            return ""

        def number(value, digits):
            # Without trailing zeros: 30 m, 0,72 m², 2,5 %.
            return formatLang(self.env, value, digits=digits).rstrip("0").rstrip(",.")

        if margin is None:
            margin = self.schldr_recalc_margin
        unit = dict(self._fields["schldr_recalc_uom"].selection).get(self.schldr_recalc_uom, "")
        amount = _("%(qty)s %(unit)s", qty=formatLang(self.env, quantity, digits=2), unit=unit)
        if margin:
            amount = _(
                "%(amount)s + %(margin)s %% = %(total)s %(unit)s",
                amount=amount,
                margin=number(margin, 2),
                total=formatLang(self.env, quantity * self._schldr_recalc_factor(margin), digits=2),
                unit=unit,
            )
        text = _(
            "%(amount)s ÷ %(size)s %(unit)s per stuk = %(pieces)s stuks",
            amount=amount,
            unit=unit,
            size=number(size, 4) or "0",
            pieces=formatLang(self.env, self._schldr_recalc_pieces(quantity, margin), digits=2),
        )
        if rounded:
            text = _("%(text)s → %(whole)s stuks op de materiaallijst", text=text,
                     whole=formatLang(self.env, self._schldr_recalculate(quantity, margin), digits=0))
        return text


# The hercalculatie fields, written on the template in one go: the check
# on them needs the unit and the dimensions of the same save.
RECALC_FIELDS = (
    "schldr_recalc", "schldr_recalc_uom", "schldr_recalc_margin",
    "schldr_length", "schldr_width", "schldr_height",
    "schldr_length_mm", "schldr_width_mm", "schldr_height_mm",
)


class ProductProduct(models.Model):
    """A variant writes the template's fields one by one (they are related
    fields), so switching hercalculatie on would be checked before the unit
    and the dimensions of the same save are there. They go to the template
    together instead."""

    _inherit = "product.product"

    @api.model
    def _schldr_split_recalc_values(self, vals):
        recalc = {key: vals[key] for key in RECALC_FIELDS if key in vals}
        rest = {key: value for key, value in vals.items() if key not in recalc}
        return recalc, rest

    @api.model_create_multi
    def create(self, vals_list):
        split = [self._schldr_split_recalc_values(vals) for vals in vals_list]
        products = super().create([rest for _recalc, rest in split])
        for product, (recalc, _rest) in zip(products, split):
            if recalc:
                product.product_tmpl_id.write(recalc)
        return products

    def write(self, vals):
        recalc, rest = self._schldr_split_recalc_values(vals)
        result = super().write(rest) if rest or not recalc else True
        if recalc:
            self.product_tmpl_id.write(recalc)
        return result
