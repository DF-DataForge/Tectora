# -*- coding: utf-8 -*-
"""The Skylux catalogue as configurable products, and the calculators of the
drawing's roof objects (koepel / dakraam and schoorsteen).

Skylux: three works items -- the dome (koepelschaal), the curb (PVC
koepelopstand) and the RWA dome (Skymax CE, with its curb) -- each with its
options and the daylight size (dagmaat) as attributes. The attributes create
their variants only when used ("dynamic"): the catalogue holds every option
and size without a product per combination. The price per option and size
comes from the Skylux price table (Dakmeting > Skylux-prijzen, filled from
the dealer price list with Odoo's import); the variant made for an order gets
that price as its own catalogue price.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Daylight sizes (dagmaat, cm) of the Skylux range.
SKYLUX_SIZES = [
    (40, 40), (50, 50), (50, 80), (60, 60), (60, 90), (70, 70), (70, 100),
    (70, 150), (80, 80), (80, 110), (80, 130), (90, 90), (90, 120), (100, 100),
    (100, 130), (100, 150), (100, 200), (110, 110), (120, 120), (120, 150),
    (120, 180), (130, 130), (130, 160), (150, 150),
]
SIZE_ATTRIBUTE = "Skylux maat (dagmaat)"

# The product lines: name, and their option attributes (name, values).
SKYLUX_LINES = {
    "dome": {
        "name": "Leveren en plaatsen van de kunststof koepelschaal Skylux",
        "attributes": [("Skylux uitvoering koepelschaal", [
            "Acrylaat dubbelwandig helder", "Acrylaat dubbelwandig opaal",
            "Acrylaat driewandig helder", "Acrylaat driewandig opaal",
            "Acrylaat vierwandig helder", "Acrylaat vierwandig opaal",
            "Acrylaat vijfwandig helder", "Acrylaat vijfwandig opaal",
            "Polycarbonaat driewandig helder", "Polycarbonaat driewandig opaal",
            "Polycarbonaat vierwandig helder", "Polycarbonaat vierwandig opaal",
            "Polycarbonaat vijfwandig helder", "Polycarbonaat vijfwandig opaal",
            "Polycarbonaat heatstop driewandig opaal",
            "Polycarbonaat heatstop vierwandig opaal",
            "Polycarbonaat heatstop vijfwandig opaal",
        ])],
    },
    "curb": {
        "name": "Leveren en plaatsen van de PVC koepelopstand Skylux",
        "attributes": [
            ("Skylux type opstand", ["16/20 EP", "16/00", "20/00 EP", "30/20", "35/30"]),
            ("Skylux bediening", ["Vast", "Opengaand"]),
        ],
    },
    "rwa": {
        "name": "Leveren en plaatsen van de RWA kunststof koepel Skylux Skymax CE "
                "(incl. PVC-opstand 16/00)",
        "attributes": [
            ("Skylux wanden", ["Driewandig", "Vierwandig", "Vijfwandig"]),
            ("Skylux kleur", ["Helder", "Opaal"]),
        ],
    },
}
LINE_SELECTION = [("dome", "Koepelschaal"), ("curb", "Koepelopstand"), ("rwa", "RWA-koepel Skymax")]


def size_label(width, length):
    return "%s x %s cm" % (width, length)


def size_of(label):
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)", label or "")
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tectora_skylux_line = fields.Selection(
        LINE_SELECTION, string="Skylux-productlijn", copy=False,
        help="Een product van de Skylux-catalogus: de prijs per uitvoering en "
        "maat staat in de Skylux-prijstabel.",
    )

    @api.model
    def _tectora_ensure_skylux_catalog(self):
        """Create (or complete) the Skylux attributes and products. Idempotent:
        run on every upgrade; existing values and products are kept."""
        Attribute = self.env["product.attribute"]
        Value = self.env["product.attribute.value"]

        def attribute(name, values):
            record = Attribute.search([("name", "=", name)], limit=1)
            if not record:
                record = Attribute.create({"name": name, "create_variant": "dynamic"})
            for sequence, value in enumerate(values):
                if not record.value_ids.filtered(lambda v: v.name == value):
                    Value.create({"attribute_id": record.id, "name": value, "sequence": sequence})
            return record

        size = attribute(SIZE_ATTRIBUTE, [size_label(w, l) for w, l in SKYLUX_SIZES])
        category = self.env["product.category"].search([("name", "=", "05. Koepels")], limit=1)
        for line, spec in SKYLUX_LINES.items():
            attributes = [attribute(name, values) for name, values in spec["attributes"]] + [size]
            template = self.with_context(active_test=False).search(
                [("tectora_skylux_line", "=", line)], limit=1
            )
            if not template:
                values = {
                    "name": spec["name"],
                    "tectora_skylux_line": line,
                    "type": "service",
                    "sale_ok": True,
                    "purchase_ok": False,
                    "list_price": 0.0,
                }
                if category:
                    values["categ_id"] = category.id
                template = self.create(values)
            for attr in attributes:
                existing = template.attribute_line_ids.filtered(lambda l: l.attribute_id == attr)
                if existing:
                    missing = attr.value_ids - existing.value_ids
                    if missing:
                        existing.value_ids = [(4, v.id) for v in missing]
                else:
                    template.write({"attribute_line_ids": [(0, 0, {
                        "attribute_id": attr.id, "value_ids": [(6, 0, attr.value_ids.ids)],
                    })]})
        return True

    def _tectora_skylux_variant(self, values):
        """The variant of this Skylux product for the attribute values
        ``values`` (product.attribute.value), made now if it does not exist
        yet (the attributes are 'dynamic')."""
        self.ensure_one()
        ptavs = self.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.product_attribute_value_id in values
        )
        variant = self._get_variant_for_combination(ptavs)
        if not variant:
            variant = self._create_product_variant(ptavs)
        if not variant:
            raise UserError(_("De variant van %s kon niet aangemaakt worden.") % self.display_name)
        return variant


class ProductProduct(models.Model):
    _inherit = "product.product"

    tectora_list_price = fields.Float(
        string="Catalogusprijs variant", digits="Product Price", copy=False,
        help="De verkoopprijs van deze variant uit de Skylux-prijstabel; "
        "vervangt de prijs van het product plus de meerprijzen van de kenmerken.",
    )

    @api.depends("list_price", "price_extra", "tectora_list_price")
    @api.depends_context("uom")
    def _compute_product_lst_price(self):
        super()._compute_product_lst_price()
        for product in self:
            if product.tectora_list_price:
                product.lst_price = product.tectora_list_price

    def _price_compute(self, price_type, *args, **kwargs):
        prices = super()._price_compute(price_type, *args, **kwargs)
        if price_type == "list_price":
            for product in self:
                if product.tectora_list_price:
                    prices[product.id] = product.tectora_list_price
        return prices


class TectoraSkyluxPrice(models.Model):
    """The Skylux price list: per product line, option and daylight size the
    sale price (and the purchase price). Filled from the dealer price list
    with Odoo's import; 'Prijstabel aanvullen' makes every row to fill in."""

    _name = "tectora.skylux.price"
    _description = "Skylux-prijs"
    _order = "line, option, size_sequence, id"

    line = fields.Selection(LINE_SELECTION, string="Productlijn", required=True, index=True)
    option = fields.Char(
        string="Uitvoering", required=True, index=True,
        help="De uitvoering zoals de calculator ze toont, bv. 'Acrylaat "
        "driewandig helder' of '16/20 EP · Opengaand'.",
    )
    size = fields.Char(string="Maat (dagmaat)", required=True, help="bv. '100 x 100 cm'.")
    size_sequence = fields.Integer(compute="_compute_size_sequence", store=True)
    price = fields.Float(string="Verkoopprijs", digits="Product Price")
    cost = fields.Float(string="Aankoopprijs", digits="Product Price")

    _unique_row = models.Constraint(
        "UNIQUE(line, option, size)",
        "Elke uitvoering en maat staat maar één keer in de Skylux-prijstabel.",
    )

    @api.depends("size")
    def _compute_size_sequence(self):
        for row in self:
            width, length = size_of(row.size)
            row.size_sequence = width * 1000 + length

    @api.model
    def _tectora_options(self, line):
        """The options of a product line, as their labels ('a · b')."""
        spec = SKYLUX_LINES[line]
        combos = [[]]
        for _name, values in spec["attributes"]:
            combos = [combo + [value] for combo in combos for value in values]
        return [" · ".join(combo) for combo in combos]

    def action_tectora_fill(self):
        """Every option and size of the catalogue as a row (price 0), to fill
        in or to export, complete and import again."""
        existing = {(r.line, r.option, r.size) for r in self.search([])}
        values = []
        for line in SKYLUX_LINES:
            for option in self._tectora_options(line):
                for width, length in SKYLUX_SIZES:
                    key = (line, option, size_label(width, length))
                    if key not in existing:
                        values.append({"line": line, "option": option, "size": key[2]})
        if values:
            self.create(values)
        return {"type": "ir.actions.client", "tag": "reload"}


def chimney_cladding(product):
    """(mode, material) of a chimney cladding product -- mode "uitbekleden"
    (the sides) or "inpakken" (the sides and the top) -- or None."""
    name = (product.name or "").lower() if product else ""
    if "schoorsteen" not in name or not ("uitbekleden" in name or "inpakken" in name):
        return None
    mode = "inpakken" if "inpakken" in name else "uitbekleden"
    match = re.search(r"\bmet (.+?)(?:\s*\+\s*aansluiting|$)", name)
    material = (match.group(1) if match else "epdm").strip()
    material = re.sub(r"(\d+)\s*cm", r"\1 cm", material)
    material = re.sub(r"(\d+)\s*mm", r"\1 mm", material).replace(" & ", " + ")
    material = material.replace("epdm", "EPDM")
    return mode, material[:1].upper() + material[1:]


def chimney_area(roof_object, product):
    """The m² a chimney cladding covers: the sides (perimeter x height), and
    the top too when the chimney is wrapped completely."""
    cladding = chimney_cladding(product)
    if not cladding:
        return 0.0
    sides = roof_object.perimeter * roof_object.height
    top = roof_object.area if cladding[0] == "inpakken" else 0.0
    return round(sides + top, 2)


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    def _tectora_object(self, object_id):
        roof_object = self.env["tectora.roof.object"].browse(int(object_id or 0)).exists()
        if not roof_object or roof_object.project_id != self:
            raise UserError(_("Dit dakobject hoort niet bij dit project."))
        return roof_object

    # ------------------------------------------------------- koepel / dakraam
    @api.model
    def _tectora_skylight_extras(self):
        """The other works of a dome (spindles, roof opening, ...): sold
        products of 05. Koepels that are not the Skylux catalogue."""
        category = self.env["product.category"].search([("name", "=", "05. Koepels")])
        if not category:
            return self.env["product.product"]
        return self.env["product.product"].search([
            ("sale_ok", "=", True), ("categ_id", "child_of", category.ids),
            ("product_tmpl_id.tectora_skylux_line", "=", False),
            ("name", "not ilike", "skylux"),
        ])

    def tectora_get_skylight_options(self, object_id):
        """The calculator of a dome: the product lines with their options,
        the sizes (the one fitting the drawn dome proposed), the prices of
        the Skylux price table, the extra works, and what the dome has."""
        self.ensure_one()
        roof_object = self._tectora_object(object_id)
        Price = self.env["tectora.skylux.price"]
        prices = {}
        for row in Price.search([]):
            prices.setdefault(row.line, {}).setdefault(row.option, {})[row.size] = {
                "price": row.price, "cost": row.cost,
            }
        sizes = [{"label": size_label(w, l), "width": w, "length": l} for w, l in SKYLUX_SIZES]
        # The drawn dome is about its daylight size: the smallest size it fits.
        drawn = sorted([roof_object.width * 100, roof_object.length * 100])
        fitting = [
            size for size in sizes
            if sorted([size["width"], size["length"]])[0] >= drawn[0] - 5
            and sorted([size["width"], size["length"]])[1] >= drawn[1] - 5
        ]
        suggested = min(fitting, key=lambda s: s["width"] * s["length"])["label"] if fitting else sizes[-1]["label"]
        Line = self.env["tectora.roof.section.product"]
        extras = []
        for product in self._tectora_skylight_extras():
            coverage = Line._coverage_from_product(product)
            extras.append({
                "id": product.id, "name": product.display_name, "price": product.lst_price,
                "uom": product.uom_id.name or "",
                "quantity": roof_object.perimeter if coverage == "edges" else 1.0,
            })
        current = {"mode": "set", "dome": "", "curb": "", "rwa": "", "size": suggested, "extras": []}
        for line in roof_object.product_line_ids:
            product = line.product_id
            kind = product.product_tmpl_id.tectora_skylux_line
            if kind:
                values = product.product_template_attribute_value_ids.product_attribute_value_id
                size = values.filtered(lambda v: v.attribute_id.name == SIZE_ATTRIBUTE)[:1]
                option = " · ".join(
                    v.name for v in values.sorted(lambda v: (v.attribute_id.sequence, v.attribute_id.id))
                    if v.attribute_id.name != SIZE_ATTRIBUTE
                )
                current[kind] = option
                if size:
                    current["size"] = size.name
                if kind == "rwa":
                    current["mode"] = "rwa"
            elif product.id in [e["id"] for e in extras]:
                current["extras"].append(product.id)
        return {
            "options": {line: Price._tectora_options(line) for line in SKYLUX_LINES},
            "labels": dict(LINE_SELECTION),
            "sizes": sizes,
            "prices": prices,
            "extras": extras,
            "current": current,
            "drawn": {"width": round(roof_object.width * 100), "length": round(roof_object.length * 100)},
        }

    def tectora_apply_skylight(self, object_id, choice):
        """Put the dome on the roof object: in mode "set" the dome (koepel-
        schaal) and the curb (opstand), in mode "rwa" the RWA dome, in the
        chosen size, as variants priced from the Skylux price table; and the
        extra works ticked. What the object had of these is replaced."""
        self.ensure_one()
        roof_object = self._tectora_object(object_id)
        Template = self.env["product.template"]
        Value = self.env["product.attribute.value"]
        Line = self.env["tectora.roof.section.product"]
        Price = self.env["tectora.skylux.price"]
        extras = self._tectora_skylight_extras()
        roof_object.product_line_ids.filtered(
            lambda l: l.product_id.product_tmpl_id.tectora_skylux_line or l.product_id in extras
        ).unlink()
        size = choice.get("size")
        wanted = [("rwa", choice.get("rwa"))] if choice.get("mode") == "rwa" else [
            ("dome", choice.get("dome")), ("curb", choice.get("curb")),
        ]
        missing = []
        created = 0
        for line, option in wanted:
            if not option:
                continue
            template = Template.search([("tectora_skylux_line", "=", line)], limit=1)
            if not template:
                raise UserError(_("De Skylux-catalogus is niet aangemaakt (upgrade de module)."))
            names = [part.strip() for part in option.split("·")]
            values = Value
            for (attribute_name, _values), name in zip(SKYLUX_LINES[line]["attributes"], names):
                values |= Value.search([("attribute_id.name", "=", attribute_name), ("name", "=", name)], limit=1)
            values |= Value.search([("attribute_id.name", "=", SIZE_ATTRIBUTE), ("name", "=", size)], limit=1)
            variant = template._tectora_skylux_variant(values)
            row = Price.search([("line", "=", line), ("option", "=", option), ("size", "=", size)], limit=1)
            if row and row.price:
                variant.write({"tectora_list_price": row.price, "standard_price": row.cost or variant.standard_price})
            else:
                missing.append("%s %s %s" % (dict(LINE_SELECTION)[line], option, size))
            Line.create({
                "object_id": roof_object.id, "product_id": variant.id,
                "coverage": "general", "quantity": 1.0,
            })
            created += 1
        for extra in choice.get("extras") or []:
            product = extras.filtered(lambda p: p.id == int(extra.get("id") or 0))
            if product:
                Line.create({
                    "object_id": roof_object.id, "product_id": product.id,
                    "coverage": Line._coverage_from_product(product),
                    "quantity": float(extra.get("quantity") or 1.0),
                })
                created += 1
        return {"lines": created, "missing": missing}

    # ------------------------------------------------------------ schoorsteen
    @api.model
    def _tectora_chimney_products(self):
        products = self.env["product.product"].search([
            ("sale_ok", "=", True), ("name", "ilike", "schoorsteen"),
            "|", ("name", "ilike", "uitbekleden"), ("name", "ilike", "inpakken"),
        ])
        return products.filtered(chimney_cladding)

    def tectora_get_chimney_options(self, object_id):
        """The calculator of a chimney: its measures, the claddings (sides
        only, or wrapped completely, per material) with the m² each covers,
        and the one it has."""
        self.ensure_one()
        roof_object = self._tectora_object(object_id)
        products = []
        for product in self._tectora_chimney_products():
            mode, material = chimney_cladding(product)
            products.append({
                "id": product.id, "name": product.display_name, "mode": mode,
                "material": material, "price": product.lst_price, "uom": product.uom_id.name or "",
            })
        products.sort(key=lambda p: (p["mode"] != "uitbekleden", p["price"], p["material"]))
        current = roof_object.product_line_ids.filtered(lambda l: chimney_cladding(l.product_id))[:1]
        return {
            "measures": {
                "length": roof_object.length, "width": roof_object.width,
                "height": roof_object.height, "perimeter": roof_object.perimeter,
                "area": roof_object.area,
            },
            "products": products,
            "current": current.product_id.id or False,
        }

    def tectora_apply_chimney(self, object_id, product_id, height=None):
        """The chimney's cladding (one product, its m² from the chimney's
        measures) and, when given, its height."""
        self.ensure_one()
        roof_object = self._tectora_object(object_id)
        if height is not None and height is not False and float(height) >= 0:
            roof_object.height = float(height)
        roof_object.product_line_ids.filtered(lambda l: chimney_cladding(l.product_id)).unlink()
        product = self._tectora_chimney_products().filtered(lambda p: p.id == int(product_id or 0))
        if product:
            self.env["tectora.roof.section.product"].create({
                "object_id": roof_object.id, "product_id": product.id, "coverage": "surface",
            })
        return {"quantity": chimney_area(roof_object, product) if product else 0.0}
