# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..lib.document import GROUPS

GROUP_LABELS = [
    ("walls", "Muren"),
    ("ceilings", "Plafonds"),
    ("floors", "Vloeren"),
    ("woodwork", "Houtwerk"),
    ("objects", "Objecten"),
]
assert [key for key, _label in GROUP_LABELS] == list(GROUPS)

MEASURES = [
    ("m2", "per m²"),
    ("m", "per lopende meter"),
    ("piece", "per stuk"),
]


class SchldrColour(models.Model):
    _name = "schldr.colour"
    _description = "Kleur"
    _order = "collection, code, name"
    _rec_names_search = ["name", "code", "collection"]

    name = fields.Char(string="Kleur", required=True)
    code = fields.Char(string="Kleurcode", help="Bv. RAL 9010, NCS S 0502-Y, 7016.")
    collection = fields.Char(
        string="Kleurwaaier", help="De waaier of het merk van de kleur: RAL, NCS, Levis, ..."
    )
    hex = fields.Char(
        string="Kleurstaal",
        default="#FFFFFF",
        help="De kleur op het scherm (#RRGGBB): zo kleuren de muren op het plan "
        "en in 3D. Een benadering, geen kleurstaal.",
    )
    active = fields.Boolean(default=True)

    @api.depends("name", "code")
    def _compute_display_name(self):
        for colour in self:
            colour.display_name = " ".join(filter(None, [colour.code, colour.name]))


class SchldrPaintSystem(models.Model):
    """What is done to a surface and sold as one works item: a preparation
    and one or more layers (primer, intermediate coat, finish), each with its
    product, its number of coats and how far a litre goes."""

    _name = "schldr.paint.system"
    _description = "Verfsysteem"
    _order = "sequence, name"

    name = fields.Char(string="Verfsysteem", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="Bedrijf")
    currency_id = fields.Many2one(
        "res.currency", compute="_compute_currency_id", string="Valuta"
    )
    product_id = fields.Many2one(
        "product.product",
        string="Werkpost op de offerte",
        required=True,
        domain="[('sale_ok', '=', True)]",
        help="Het product dat verkocht wordt wanneer dit systeem op een "
        "oppervlak staat: de werkpost (schilderwerk per m², per meter of per "
        "stuk) met zijn prijs. De verf zelf staat niet op de offerte; ze komt "
        "uit de lagen op de materiaallijst.",
    )
    sale_measure = fields.Selection(
        MEASURES,
        string="Verkocht",
        required=True,
        default="m2",
        help="Waarin de werkpost gemeten wordt: de oppervlakte van het "
        "oppervlak, zijn lengte (plinten, omlijstingen) of het aantal "
        "(deuren, radiatoren).",
    )
    on_walls = fields.Boolean(string="Muren", default=True)
    on_ceilings = fields.Boolean(string="Plafonds")
    on_floors = fields.Boolean(string="Vloeren")
    on_woodwork = fields.Boolean(string="Houtwerk")
    on_objects = fields.Boolean(string="Objecten")
    layer_ids = fields.One2many(
        "schldr.paint.system.layer", "system_id", string="Lagen", copy=True
    )
    prep_hours = fields.Float(
        string="Uren voorbereiding per eenheid",
        digits=(16, 3),
        help="Schuren, plamuren, afplakken: uren per verkochte eenheid, los "
        "van de lagen.",
    )
    paint_hours = fields.Float(
        string="Uren schilderen per eenheid",
        compute="_compute_totals",
        digits=(16, 3),
        help="De lagen samen: lagen × uren per laag.",
    )
    material_cost = fields.Monetary(
        string="Materiaalkost per m²",
        compute="_compute_totals",
        currency_field="currency_id",
        help="Kostprijs van de verf van alle lagen voor één m² oppervlak.",
    )
    description = fields.Text(string="Omschrijving op de offerte")

    _product_unique = models.Constraint(
        "UNIQUE(product_id)",
        "Elke werkpost hoort bij één verfsysteem: de uren van het systeem "
        "staan op het product.",
    )

    def _compute_currency_id(self):
        for system in self:
            system.currency_id = (system.company_id or self.env.company).currency_id

    @api.depends(
        "layer_ids.coats", "layer_ids.hours_per_coat", "layer_ids.spreading_rate",
        "layer_ids.waste_pct", "layer_ids.dilution_pct", "layer_ids.product_id.standard_price",
    )
    def _compute_totals(self):
        for system in self:
            system.paint_hours = sum(
                layer.coats * layer.hours_per_coat for layer in system.layer_ids
            )
            system.material_cost = sum(
                layer._units_per_m2() * layer.product_id.standard_price
                for layer in system.layer_ids
            )

    def groups(self):
        """The surface groups this system can be put on."""
        self.ensure_one()
        return [group for group in GROUPS if self["on_%s" % group]]

    @api.constrains("on_walls", "on_ceilings", "on_floors", "on_woodwork", "on_objects")
    def _check_groups(self):
        for system in self:
            if not system.groups():
                raise ValidationError(_(
                    "Kies waarop %(system)s gezet kan worden: muren, plafonds, "
                    "vloeren, houtwerk of objecten.", system=system.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        systems = super().create(vals_list)
        systems._schldr_push_hours()
        return systems

    def write(self, vals):
        result = super().write(vals)
        if {"prep_hours", "layer_ids", "product_id"} & set(vals):
            self._schldr_push_hours()
        return result

    def _schldr_push_hours(self):
        """The hours of the system are the time norms of its works item, so
        the estimate of an order line (quantity x norm) and the tasks sized
        from it follow the system."""
        for system in self:
            template = system.product_id.product_tmpl_id
            values = {
                "schldr_hours_preparation_per_uom": system.prep_hours,
                "schldr_hours_execution_per_uom": system.paint_hours,
            }
            changed = {
                key: value for key, value in values.items()
                if abs(template[key] - value) > 1e-6
            }
            if changed:
                template.write(changed)

    def _schldr_recipe(self):
        """{id: {"layers": [...]}} in the shape lib.measure.material_needs
        reads."""
        return {
            system.id: {
                "layers": [
                    {
                        "product": layer.product_id.id,
                        "coats": layer.coats,
                        "rate": layer.spreading_rate,
                        "dilution": layer.dilution_pct,
                        "waste": layer.waste_pct,
                        "tinted": layer.tinted,
                    }
                    for layer in system.layer_ids
                ]
            }
            for system in self
        }


class SchldrPaintSystemLayer(models.Model):
    _name = "schldr.paint.system.layer"
    _description = "Laag van een verfsysteem"
    _order = "system_id, sequence, id"

    system_id = fields.Many2one(
        "schldr.paint.system", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    role = fields.Selection(
        [
            ("prep", "Voorbereiding"),
            ("primer", "Grondlaag"),
            ("intermediate", "Tussenlaag"),
            ("finish", "Eindlaag"),
        ],
        string="Laag",
        required=True,
        default="finish",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        help="De verf (of plamuur, primer, vernis) van deze laag. Leeg voor "
        "een laag die enkel werk is.",
    )
    uom_id = fields.Many2one(related="product_id.uom_id", string="Eenheid")
    coats = fields.Integer(string="Aantal lagen", default=1, required=True)
    spreading_rate = fields.Float(
        string="Rendement (m² per eenheid)",
        digits=(16, 2),
        default=10.0,
        help="Hoeveel m² één eenheid van het product (één liter) dekt in één "
        "laag, zoals op de technische fiche.",
    )
    dilution_pct = fields.Float(
        string="Verdunning (%)",
        help="Water of verdunner die erbij gaat: 10 betekent dat één liter "
        "product 1,1 liter verf geeft.",
    )
    waste_pct = fields.Float(
        string="Verlies (%)", default=5.0,
        help="Wat in de rol, de bak en de pot achterblijft.",
    )
    hours_per_coat = fields.Float(
        string="Uren per laag", digits=(16, 3),
        help="Uren per verkochte eenheid van het systeem, voor één laag.",
    )
    tinted = fields.Boolean(
        string="Op kleur",
        default=True,
        help="Aangevinkt wordt het product per kleur besteld en geteld; "
        "uitgevinkt (primer, plamuur) is het voor alle kleuren hetzelfde.",
    )

    _coats_positive = models.Constraint(
        "CHECK(coats >= 0)", "Het aantal lagen kan niet negatief zijn."
    )

    def _units_per_m2(self):
        """Units of the product one m2 of surface takes, all coats."""
        self.ensure_one()
        if not self.product_id or not self.spreading_rate:
            return 0.0
        return (
            self.coats * (1.0 + self.waste_pct / 100.0)
            / self.spreading_rate / (1.0 + self.dilution_pct / 100.0)
        )

    @api.constrains("spreading_rate", "product_id")
    def _check_rate(self):
        for layer in self:
            if layer.product_id and layer.spreading_rate <= 0:
                raise ValidationError(_(
                    "Geef het rendement van %(product)s (m² per eenheid).",
                    product=layer.product_id.display_name,
                ))


class SchldrPackSize(models.Model):
    _name = "schldr.pack.size"
    _description = "Verpakking van een verfproduct"
    _order = "product_tmpl_id, volume"

    product_tmpl_id = fields.Many2one(
        "product.template", required=True, ondelete="cascade", index=True
    )
    volume = fields.Float(
        string="Inhoud", digits=(16, 3), required=True,
        help="In de eenheid van het product: 2,5 voor een pot van 2,5 liter.",
    )
    price = fields.Float(
        string="Inkoopprijs", digits="Product Price",
        help="Prijs van één verpakking. Staat er op elke verpakking een "
        "prijs, dan kiest de materiaallijst de goedkoopste combinatie; anders "
        "gaat ze ervan uit dat een grotere pot per liter goedkoper is.",
    )

    _volume_positive = models.Constraint(
        "CHECK(volume > 0)", "De inhoud van een verpakking is groter dan nul."
    )


class SchldrElementType(models.Model):
    """A door, window or radiator as it is put on the plan with one click."""

    _name = "schldr.element.type"
    _description = "Standaardelement op het plan"
    _order = "kind, sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind = fields.Selection(
        [
            ("door", "Deur"),
            ("window", "Raam"),
            ("passage", "Doorgang"),
            ("exclusion", "Uitsparing (niet te schilderen)"),
            ("radiator", "Radiator"),
        ],
        string="Soort",
        required=True,
        default="door",
    )
    width = fields.Integer(string="Breedte (mm)", default=930)
    height = fields.Integer(string="Hoogte (mm)", default=2115)
    sill = fields.Integer(string="Borstwering (mm)", help="Hoogte van de onderkant boven de vloer.")
    reveal = fields.Integer(
        string="Dagkant (mm)",
        help="Diepte van de dagkanten die mee geschilderd worden; ze tellen "
        "bij de muur.",
    )
    has_leaf = fields.Boolean(string="Deurblad schilderen")
    has_frame = fields.Boolean(string="Omlijsting schilderen")
    frame_girth = fields.Integer(
        string="Ontwikkelde breedte omlijsting (mm)", default=150,
        help="De breedte van de omlijsting als ze plat gelegd wordt: zo wordt "
        "haar lengte een oppervlakte voor de verf.",
    )
    factor = fields.Float(
        string="Oppervlaktefactor",
        default=1.0,
        help="Breedte × hoogte × deze factor is de te schilderen oppervlakte: "
        "2,5 voor een paneelradiator met lamellen, 1,1 voor een deur met "
        "panelen.",
    )

    def _schldr_preset(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "sill": self.sill,
            "reveal": self.reveal,
            "leaf": self.has_leaf,
            "frame": self.has_frame,
            "frame_girth": self.frame_girth,
            "factor": self.factor,
        }
