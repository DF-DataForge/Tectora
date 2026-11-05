# -*- coding: utf-8 -*-
"""The standard build-up of a flat roof surface (dampscherm, isolatie,
dakbedekking) and the EPDM sheets it takes, from the drawing.

The drawing's product picker offers a "Dakopbouw" tab for a roof surface:
one product per layer, chosen by type, thickness and fixing instead of from a
list of a hundred insulation boards, applied to the surface (and any other
surfaces ticked) at once. The EPDM sheets follow from the surfaces: one sheet
per surface -- a seam (naad) cuts a surface in two, so it is the joint between
two sheets -- sized on the roof surface inside the roof edges, plus per side
the upstand (opstand) and the width of the roof edge (dakrand) it runs over,
plus a margin.
"""
import math
import re

from odoo import _, api, fields, models

from .roof_project import DEFAULT_SCALE_M_PER_PX, _inset_polygon_px

# The widest EPDM roll in the catalogue (15,25 m): a wider sheet needs a joint.
EPDM_MAX_WIDTH = 15.25

LAYERS = ("vapour", "insulation", "membrane")

# Per layer: the category names (under 04. Opbouwwerken plat dak) and, for
# products not filed yet, the words in their name.
LAYER_CATEGORIES = {
    "vapour": ["Dampscherm"],
    "insulation": ["Isolatie"],
    "membrane": ["Dakbedekking"],
}
LAYER_NAMES = {
    "vapour": ["dampscherm"],
    "insulation": ["isolatie type:"],
    "membrane": ["dakbedekking type:"],
}

FIXINGS = (
    ("verkleef", "verkleefd"),
    ("mechanis", "mechanisch"),
    ("losligg", "losliggend"),
    ("geballast", "geballast"),
)


def _number(text):
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _fixing(name):
    lowered = (name or "").lower()
    for stem, label in FIXINGS:
        if stem in lowered:
            return label
    return ""


def _round_up(value, step=0.05):
    return math.ceil(round(value / step, 6)) * step


def epdm_sheet_size(points, extensions):
    """Length and width (m) of the sheet covering polygon ``points`` (m),
    with ``extensions[i]`` (m) added beyond side i (from points[i] to
    points[i+1]).

    The sheet is the smallest rectangle around the surface (aligned with one
    of its sides, so a roof drawn at an angle gets an angled sheet); each of
    its four sides is moved out by the largest extension of the polygon sides
    lying on it. Returns (length, width), length the longer.
    """
    n = len(points)
    if n < 3:
        return 0.0, 0.0
    best = None
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        size = math.hypot(bx - ax, by - ay)
        if size < 1e-9:
            continue
        ux, uy = (bx - ax) / size, (by - ay) / size
        us = [x * ux + y * uy for x, y in points]
        vs = [-x * uy + y * ux for x, y in points]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0] - 1e-9:
            best = (area, us, vs)
    if best is None:
        return 0.0, 0.0
    _area, us, vs = best

    def side_extension(values, target):
        extent = max(values) - min(values)
        tolerance = max(0.02, extent * 0.01)
        on_side = [
            extensions[i] for i in range(n)
            if abs(values[i] - target) <= tolerance
            and abs(values[(i + 1) % n] - target) <= tolerance
        ]
        if not on_side:
            # Only a corner touches this side: the sides meeting there.
            on_side = [
                extensions[i] for i in range(n)
                if abs(values[i] - target) <= tolerance
                or abs(values[(i + 1) % n] - target) <= tolerance
            ]
        return max(on_side) if on_side else 0.0

    along = (max(us) - min(us)) + side_extension(us, min(us)) + side_extension(us, max(us))
    across = (max(vs) - min(vs)) + side_extension(vs, min(vs)) + side_extension(vs, max(vs))
    return max(along, across), min(along, across)


class ResConfigSettings(models.TransientModel):
    """The default build-up, as system parameters: no column on the company,
    which every request reads."""
    _inherit = "res.config.settings"

    tectora_buildup_vapour_id = fields.Many2one(
        "product.product", string="Standaard dampscherm",
        config_parameter="tectora_roof.buildup_vapour_id",
        help="Voorgesteld in de dakopbouw van een nieuw dakvlak.",
    )
    tectora_buildup_insulation_id = fields.Many2one(
        "product.product", string="Standaard isolatie",
        config_parameter="tectora_roof.buildup_insulation_id",
    )
    tectora_buildup_membrane_id = fields.Many2one(
        "product.product", string="Standaard dakbedekking",
        config_parameter="tectora_roof.buildup_membrane_id",
    )
    tectora_epdm_margin = fields.Float(
        string="Marge EPDM-doek per zijde (m)", digits=(16, 2),
        config_parameter="tectora_roof.epdm_margin", default=0.10,
        help="Komt bij elk doek op elke zijde bij, bovenop de opstand en de "
        "breedte van de dakrand: om over de rand te plooien en vast te zetten.",
    )


class TectoraRoofEpdmSheet(models.Model):
    _inherit = "tectora.roof.epdm.sheet"

    section_id = fields.Many2one(
        "tectora.roof.section", string="Dakvlak", ondelete="cascade", index=True,
        help="Het dakvlak waarvoor het doek berekend werd; een herberekening "
        "vervangt het. Doeken zonder dakvlak zijn met de hand ingegeven.",
    )


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    buildup_vapour_id = fields.Many2one(
        "product.product", string="Dampscherm", copy=False,
        help="Laatst toegepast in de dakopbouw; voorgesteld voor de volgende vlakken.",
    )
    buildup_insulation_id = fields.Many2one("product.product", string="Isolatie", copy=False)
    buildup_membrane_id = fields.Many2one("product.product", string="Dakbedekking", copy=False)

    @api.model
    def _tectora_buildup_defaults(self):
        """The company's default build-up (Instellingen, system parameters)."""
        params = self.env["ir.config_parameter"].sudo()
        Product = self.env["product.product"]

        def param(key):
            # Odoo 20 reads parameters with get_str (get_param is gone).
            getter = getattr(params, "get_str", None) or getattr(params, "get_param")
            return getter("tectora_roof.%s" % key) or ""

        def product(key):
            try:
                product_id = int(param(key) or 0)
            except (TypeError, ValueError):
                return False
            return Product.browse(product_id).exists().id or False

        raw_margin = param("epdm_margin")
        try:
            margin = float(raw_margin) if raw_margin != "" else 0.10
        except (TypeError, ValueError):
            margin = 0.10
        return {
            "vapour": product("buildup_vapour_id"),
            "insulation": product("buildup_insulation_id"),
            "membrane": product("buildup_membrane_id"),
            "margin": max(margin, 0.0),
        }

    # ------------------------------------------------------------- products
    @api.model
    def _tectora_is_area_uom(self, uom):
        if not uom:
            return False
        square = self.env.ref("uom.product_uom_square_meter", raise_if_not_found=False)
        name = (uom.name or "").lower().replace(" ", "")
        return uom == square or name in ("m²", "m2")

    @api.model
    def _tectora_layer_products(self, layer):
        """The products of a build-up layer: sold per m², in the layer's
        category (or named so, until the products are filed)."""
        Category = self.env["product.category"]
        categories = Category.search([("name", "in", LAYER_CATEGORIES[layer])]).filtered(
            lambda c: "afbraak" not in (c.complete_name or "").lower()
        )
        domain = [("sale_ok", "=", True)]
        alternatives = [[("name", "ilike", word)] for word in LAYER_NAMES[layer]]
        if categories:
            alternatives.append([("categ_id", "child_of", categories.ids)])
        domain += ["|"] * (len(alternatives) - 1) + [term for alt in alternatives for term in alt]
        products = self.env["product.product"].search(domain)
        return products.filtered(
            lambda p: self._tectora_is_area_uom(p.uom_id)
            and not re.search(r"verwijder|afbraak", (p.name or "").lower())
        )

    @api.model
    def _tectora_layer_info(self, layer, product):
        """What the dialog chooses a product by: its type, thickness and
        fixing, read from the catalogue's names ("Leveren en plaatsen isolatie
        type: Unilin Utherm Roof PIR dikte: 10cm (600x1200) verkleefd")."""
        name = product.name or ""
        info = {
            "id": product.id,
            "name": product.display_name,
            "code": product.default_code or "",
            "price": product.lst_price,
            "uom": product.uom_id.name or "",
            "category": product.categ_id.name or "",
            "fixing": _fixing(name),
            "type": "",
            "thickness": 0.0,
            "thickness_label": "",
            "variant": "",
        }
        typed = re.search(r"type:\s*(.+)$", name, re.IGNORECASE)
        rest = typed.group(1) if typed else name
        if layer == "insulation":
            match = re.search(r"type:\s*(.+?)\s+dikte:\s*([\d.,]+)\s*(mm|cm)", name, re.IGNORECASE)
            if match:
                info["type"] = match.group(1).strip()
                value = _number(match.group(2))
                info["thickness"] = value * 10 if match.group(3).lower() == "cm" else value
                info["thickness_label"] = "%s %s" % (match.group(2), match.group(3).lower())
            variant = re.search(r"\(([^)]*)\)", name)
            if variant:
                info["variant"] = variant.group(1).strip()
        elif layer == "membrane":
            thickness = re.search(r"([\d]+[.,]?\d*)\s*mm", rest, re.IGNORECASE)
            if thickness:
                info["thickness"] = _number(thickness.group(1))
                info["thickness_label"] = "%s mm" % thickness.group(1)
                rest = rest[:thickness.start()]
            info["type"] = re.sub(r"\s+", " ", rest).strip(" ,-") or name
        else:
            klass = re.search(r"klasse\s+(E\d)", name, re.IGNORECASE)
            info["type"] = rest.strip()
            info["variant"] = klass.group(1).upper() if klass else ""
        if not info["type"]:
            info["type"] = product.categ_id.name or name
        return info

    def tectora_get_buildup_options(self):
        """The products per layer for the "Dakopbouw" dialog, with the
        build-up last applied on this project (else the company's) chosen."""
        self.ensure_one()
        defaults = self._tectora_buildup_defaults()
        options = {}
        for layer in LAYERS:
            infos = [self._tectora_layer_info(layer, p) for p in self._tectora_layer_products(layer)]
            infos.sort(key=lambda i: (i["type"].lower(), i["thickness"], i["variant"], i["fixing"], i["name"]))
            options[layer] = infos
        current = {
            "vapour": self.buildup_vapour_id.id or defaults["vapour"],
            "insulation": self.buildup_insulation_id.id or defaults["insulation"],
            "membrane": self.buildup_membrane_id.id or defaults["membrane"],
        }
        return {
            "options": options,
            "current": current,
            "margin": defaults["margin"],
            "max_width": EPDM_MAX_WIDTH,
        }

    # ---------------------------------------------------------------- apply
    def _tectora_buildup_sections(self, section_ids):
        return self.env["tectora.roof.section"].browse(section_ids or []).exists().filtered(
            lambda s: s.project_id == self
        )

    def tectora_apply_buildup(self, section_ids, vapour_id=False, insulation_id=False,
                              membrane_id=False, sheets=False, margin=None):
        """Put the build-up on the surfaces: per layer chosen, the surface's
        product of that layer is replaced by the chosen one (a layer left
        empty is not touched). With ``sheets`` the EPDM sheets of those
        surfaces are calculated as well. Remembers the choice for the next
        surface."""
        self.ensure_one()
        sections = self._tectora_buildup_sections(section_ids)
        Line = self.env["tectora.roof.section.product"]
        chosen = {"vapour": vapour_id, "insulation": insulation_id, "membrane": membrane_id}
        created = 0
        for layer, product_id in chosen.items():
            if not product_id:
                continue
            layer_products = self._tectora_layer_products(layer)
            for section in sections:
                lines = section.product_line_ids.filtered(
                    lambda l: l.coverage == "surface" and not l.edge_index
                )
                stale = lines.filtered(
                    lambda l: l.product_id in layer_products and l.product_id.id != product_id
                )
                stale.unlink()
                if not lines.filtered(lambda l: l.product_id.id == product_id):
                    Line.create({
                        "section_id": section.id,
                        "product_id": product_id,
                        "coverage": "surface",
                        "edge_index": 0,
                    })
                    created += 1
        values = {
            "buildup_%s_id" % layer: product_id
            for layer, product_id in chosen.items() if product_id
        }
        if values:
            self.write(values)
        result = {"lines": created, "sheets": []}
        if sheets:
            result["sheets"] = self.tectora_compute_epdm_sheets(section_ids, margin=margin)
            if membrane_id:
                info = self._tectora_layer_info("membrane", self.env["product.product"].browse(membrane_id))
                if info["thickness"] and "epdm" in info["name"].lower():
                    self.epdm_thickness = info["thickness"]
        return result

    # ----------------------------------------------------------- EPDM sheets
    def _tectora_section_shape(self, section, cache):
        """(points in m, per-side extension in m without margin) of a
        surface, from the plan of its roof."""
        source = self
        if section.roof_id and section.roof_id != self.active_roof_id:
            source = section.roof_id
        key = (source._name, source.id)
        if key not in cache:
            shapes = self._parse_canvas_shapes(source.canvas_data or "")
            cache[key] = (
                {shape["id"]: shape for shape in shapes},
                source.scale_m_per_px or DEFAULT_SCALE_M_PER_PX,
            )
        shapes, scale = cache[key]
        shape = shapes.get(section.canvas_ref or "")
        if not shape or shape["kind"] != "section" or len(shape["points"]) < 3:
            return None
        points = shape["points"]
        n = len(points)
        widths = [max(shape["edge_widths"].get(i, 0.0), 0.0) for i in range(n)]
        upstands = [max(shape["edge_upstands"].get(i, 0.0), 0.0) for i in range(n)]
        # The sheet lies on the surface inside the roof edges, then runs up
        # the upstand and over the edge's width.
        # The drawn outline includes the roof edges (the surface itself is
        # the outline less their widths): the sheet covers the surface, runs
        # up the upstand and over the edge's width -- the outline plus the
        # upstand. When the inset degenerates, the outline is all there is.
        inner = _inset_polygon_px(points, [w / scale for w in widths]) if any(widths) else None
        if inner:
            polygon = inner
            extensions = [upstands[i] + widths[i] for i in range(n)]
        else:
            polygon = points
            extensions = upstands
        return [(x * scale, y * scale) for x, y in polygon], extensions

    def _tectora_epdm_sheet_values(self, section_ids, margin=None):
        self.ensure_one()
        if margin is None or margin is False:
            margin = self._tectora_buildup_defaults()["margin"]
        margin = max(float(margin or 0.0), 0.0)
        several_roofs = len(self.roof_ids) > 1
        cache = {}
        result = []
        for section in self._tectora_buildup_sections(section_ids).sorted(lambda s: (s.roof_id.id or 0, s.name or "", s.id)):
            shape = self._tectora_section_shape(section, cache)
            if not shape:
                continue
            polygon, extensions = shape
            length, width = epdm_sheet_size(polygon, [e + margin for e in extensions])
            length, width = _round_up(length), _round_up(width)
            name = section.name or _("Dakvlak")
            if several_roofs and section.roof_id:
                name = "%s · %s" % (section.roof_id.name, name)
            notes = [_("opstand en dakrand inbegrepen, marge %s cm per zijde") % round(margin * 100)]
            if width > EPDM_MAX_WIDTH:
                notes.append(_("breder dan %s m: met een naad uit twee rollen") % EPDM_MAX_WIDTH)
            result.append({
                "section_id": section.id,
                "name": _("EPDM-doek %s") % name,
                "length": round(length, 2),
                "width": round(width, 2),
                "area": round(length * width, 2),
                "note": "; ".join(notes),
            })
        return result

    def tectora_preview_epdm_sheets(self, section_ids, margin=None):
        """The sheets the surfaces take, without saving them."""
        self.ensure_one()
        return self._tectora_epdm_sheet_values(section_ids, margin)

    def tectora_compute_epdm_sheets(self, section_ids, margin=None):
        """(Re)calculate the EPDM sheets of the surfaces: the sheets
        calculated for them before are replaced, sheets entered by hand stay."""
        self.ensure_one()
        values = self._tectora_epdm_sheet_values(section_ids, margin)
        Sheet = self.env["tectora.roof.epdm.sheet"]
        Sheet.search([
            ("project_id", "=", self.id),
            ("section_id", "in", self._tectora_buildup_sections(section_ids).ids),
        ]).unlink()
        last = max(self.epdm_sheet_ids.mapped("sequence") or [0])
        for index, sheet in enumerate(values, start=1):
            Sheet.create({
                "project_id": self.id,
                "section_id": sheet["section_id"],
                "sequence": last + index,
                "name": sheet["name"],
                "length": sheet["length"],
                "width": sheet["width"],
                "note": sheet["note"],
            })
        return values
