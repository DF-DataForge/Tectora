# -*- coding: utf-8 -*-
"""The standard build-up of a flat roof surface (dampscherm, isolatie,
dakbedekking) and the EPDM sheets it takes, from the drawing.

The drawing's product picker offers a "Dakopbouw" tab for a roof surface:
one product per layer, chosen by type, thickness and fixing instead of from a
list of a hundred insulation boards, applied to the surface (and any other
surfaces ticked) at once. The EPDM sheets follow from the surfaces: a surface
stays one section (its products, its quantities), and the seams (naden)
drawn on it divide it into sheets -- the joints between them. Each sheet is
sized on its part of the surface inside the roof edges, plus per side the
upstand (opstand) and the width of the roof edge (dakrand) it runs over, plus
a margin; a side along a seam gets the margin only, as the overlap.
"""
import math
import re

from odoo import _, api, fields, models

from .roof_project import (
    DEFAULT_SCALE_M_PER_PX,
    _inset_polygon_px,
    _point_in_polygon,
    _polygon_area_px,
)

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


def _segment_intersection(a, b, c, d):
    """Where segments a-b and c-d cross: (point, t along a-b, u along c-d),
    or None (mirror of the drawing's segmentIntersection)."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-9:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t = (qx * sy - qy * sx) / denom
    u = (qx * ry - qy * rx) / denom
    eps = 1e-7
    if t < -eps or t > 1 + eps or u < -eps or u > 1 + eps:
        return None
    return (a[0] + rx * t, a[1] + ry * t), t, u


def split_polygon_by_polyline(polygon, polyline):
    """The two parts of ``polygon`` on either side of the open ``polyline``
    (a seam), or None when it does not cross cleanly. Seam ends stopping
    inside the polygon are extended to its outline. Mirror of the drawing's
    splitPolygonByPolyline."""
    n = len(polygon)
    if n < 3 or len(polyline) < 2:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    reach = ((max(xs) - min(xs)) + (max(ys) - min(ys))) * 4 + 10
    line = [tuple(p) for p in polyline]

    def extend(start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy) or 1.0
        return (end[0] + dx / length * reach, end[1] + dy / length * reach)

    if _point_in_polygon(line[0], polygon):
        line[0] = extend(line[1], line[0])
    if _point_in_polygon(line[-1], polygon):
        line[-1] = extend(line[-2], line[-1])
    crossings = []
    for k in range(len(line) - 1):
        for i in range(n):
            hit = _segment_intersection(line[k], line[k + 1], polygon[i], polygon[(i + 1) % n])
            if hit:
                crossings.append({"seg": k, "t": hit[1], "edge": i, "u": hit[2], "point": hit[0]})
    if len(crossings) < 2:
        return None
    crossings.sort(key=lambda c: (c["seg"], c["t"]))
    entry, exit_ = crossings[0], crossings[-1]
    if entry["seg"] == exit_["seg"] and abs(entry["t"] - exit_["t"]) < 1e-6:
        return None
    inside = [line[k] for k in range(entry["seg"] + 1, exit_["seg"] + 1)]

    def walk(from_edge, to_edge, from_u, to_u):
        count = (to_edge - from_edge + n) % n
        if from_edge == to_edge and to_u < from_u:
            count = n
        return [polygon[(from_edge + step) % n] for step in range(1, count + 1)]

    part_a = [entry["point"]] + walk(entry["edge"], exit_["edge"], entry["u"], exit_["u"]) \
        + [exit_["point"]] + list(reversed(inside))
    part_b = [exit_["point"]] + walk(exit_["edge"], entry["edge"], exit_["u"], entry["u"]) \
        + [entry["point"]] + inside

    def clean(part):
        out = []
        for p in part:
            if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 0.5:
                out.append(p)
        if len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 0.5:
            out.pop()
        return out

    a, b = clean(part_a), clean(part_b)
    total = _polygon_area_px(polygon)
    if len(a) < 3 or len(b) < 3:
        return None
    if _polygon_area_px(a) < total * 0.01 or _polygon_area_px(b) < total * 0.01:
        return None
    return a, b


def split_by_seams(polygon, seams):
    """``polygon`` cut by every seam (open polylines) that crosses it: the
    EPDM sheets of one roof surface."""
    pieces = [list(polygon)]
    for seam in seams:
        result = []
        for piece in pieces:
            parts = split_polygon_by_polyline(piece, seam)
            result.extend(parts if parts else [piece])
        pieces = result
    return pieces


def _on_segment(point, a, b, tolerance):
    """Whether ``point`` lies on segment a-b (within ``tolerance``)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return math.hypot(point[0] - a[0], point[1] - a[1]) <= tolerance
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length)
    if t < -tolerance / length or t > 1 + tolerance / length:
        return False
    distance = abs((point[0] - a[0]) * dy - (point[1] - a[1]) * dx) / length
    return distance <= tolerance


def piece_sources(piece, outline, tolerance=1.0):
    """Per side of ``piece`` (a part of ``outline``): the index of the
    outline side it lies on, or None for a side along a seam."""
    n = len(outline)
    result = []
    for i in range(len(piece)):
        p, q = piece[i], piece[(i + 1) % len(piece)]
        source = None
        for j in range(n):
            a, b = outline[j], outline[(j + 1) % n]
            if _on_segment(p, a, b, tolerance) and _on_segment(q, a, b, tolerance):
                source = j
                break
        result.append(source)
    return result


def piece_extensions(piece, outline, extensions, tolerance=1.0):
    """Per side of ``piece``: the extension of the outline side it lies on,
    or 0 for a side along a seam (the overlap with the next sheet)."""
    return [
        extensions[j] if j is not None else 0.0
        for j in piece_sources(piece, outline, tolerance)
    ]


def sheet_layout(points, extensions):
    """How the sheet covering polygon ``points`` (m) is laid out: the
    smallest rectangle around it (aligned with one of its sides, so a roof
    drawn at an angle gets an angled sheet), each of its four sides moved out
    by the largest ``extensions`` of the polygon sides lying on it.

    Returns two dimensions, longest first, each {"base": extent of the
    surface, "ends": [polygon side index or None, same], "size": total}."""
    n = len(points)
    if n < 3:
        return []
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
        return []
    _area, us, vs = best

    def end_side(values, target):
        """The polygon side that sets the extension at this end."""
        extent = max(values) - min(values)
        tolerance = max(0.02, extent * 0.01)
        on_side = [
            i for i in range(n)
            if abs(values[i] - target) <= tolerance
            and abs(values[(i + 1) % n] - target) <= tolerance
        ]
        if not on_side:
            # Only a corner touches this side: the sides meeting there.
            on_side = [
                i for i in range(n)
                if abs(values[i] - target) <= tolerance
                or abs(values[(i + 1) % n] - target) <= tolerance
            ]
        return max(on_side, key=lambda i: extensions[i]) if on_side else None

    dimensions = []
    for values in (us, vs):
        ends = [end_side(values, min(values)), end_side(values, max(values))]
        base = max(values) - min(values)
        size = base + sum(extensions[i] for i in ends if i is not None)
        dimensions.append({"base": base, "ends": ends, "size": size})
    dimensions.sort(key=lambda d: -d["size"])
    return dimensions


def epdm_sheet_size(points, extensions):
    """Length and width (m) of the sheet covering polygon ``points`` (m),
    with ``extensions[i]`` (m) added beyond side i (see sheet_layout).
    Returns (length, width), length the longer."""
    layout = sheet_layout(points, extensions)
    if not layout:
        return 0.0, 0.0
    return layout[0]["size"], layout[1]["size"]


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
    tectora_quote_notes = fields.Char(
        string="Standaard algemene nota's",
        config_parameter="tectora_roof.quote_notes",
        help="De tekst waarmee de Algemene nota's van een nieuw dakproject "
        "beginnen (laatste segment van de offerte).",
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
                # Only the lines that are left: the deleted ones can no
                # longer be read.
                if not (lines - stale).filtered(lambda l: l.product_id.id == product_id):
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
        """The sheets of a surface, from the plan of its roof: per part
        between the seams, (points in m, per-side extension in m without
        margin)."""
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
        seams = [s["points"] for s in shapes.values() if s["kind"] == "seam"]
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
            polygon = [tuple(p) for p in points]
            extensions = list(upstands)
        # The seams on the surface are the joints between its sheets: one
        # sheet per part; a side along a seam only gets the margin (overlap).
        # Per side of a part: what it adds beyond the surface.
        sheets = []
        for piece in split_by_seams(polygon, seams):
            sides = []
            for j in piece_sources(piece, polygon):
                if j is None:
                    sides.append({"label": _("naad"), "seam": True, "upstand": 0.0, "width": 0.0})
                else:
                    sides.append({
                        "label": "Z%s" % (j + 1),
                        "seam": False,
                        "upstand": upstands[j],
                        "width": widths[j] if inner else 0.0,
                    })
            sheets.append(([(x * scale, y * scale) for x, y in piece], sides))
        return sheets

    def _tectora_epdm_sheet_values(self, section_ids, margin=None):
        self.ensure_one()
        if margin is None or margin is False:
            margin = self._tectora_buildup_defaults()["margin"]
        margin = max(float(margin or 0.0), 0.0)
        several_roofs = len(self.roof_ids) > 1
        cache = {}
        result = []
        for section in self._tectora_buildup_sections(section_ids).sorted(lambda s: (s.roof_id.id or 0, s.name or "", s.id)):
            sheets = self._tectora_section_shape(section, cache)
            if not sheets:
                continue
            name = section.name or _("Dakvlak")
            if several_roofs and section.roof_id:
                name = "%s · %s" % (section.roof_id.name, name)
            for index, (polygon, sides) in enumerate(sheets, start=1):
                extensions = [side["upstand"] + side["width"] + margin for side in sides]
                layout = sheet_layout(polygon, extensions)
                if not layout:
                    continue
                dimensions = []
                for label, dimension in zip((_("Lengte"), _("Breedte")), layout):
                    ends = []
                    for side_index in dimension["ends"]:
                        if side_index is None:
                            continue
                        side = sides[side_index]
                        ends.append({
                            "label": side["label"],
                            "seam": side["seam"],
                            "upstand": round(side["upstand"], 2),
                            "width": round(side["width"], 2),
                            "margin": round(margin, 2),
                            "total": round(extensions[side_index], 2),
                        })
                    dimensions.append({
                        "label": label,
                        "base": round(dimension["base"], 2),
                        "ends": ends,
                        "raw": round(dimension["size"], 2),
                        "size": round(_round_up(dimension["size"]), 2),
                    })
                length, width = dimensions[0]["size"], dimensions[1]["size"]
                surface = _polygon_area_px(polygon)
                waste = length * width - surface
                notes = [self._tectora_dimension_text(d) for d in dimensions]
                notes.append(_("vlak %(surface)s m², doek %(sheet)s m², snijverlies %(waste)s m²",
                               surface="%.2f" % surface, sheet="%.2f" % (length * width),
                               waste="%.2f" % waste))
                if width > EPDM_MAX_WIDTH:
                    notes.append(_("breder dan %s m: met een naad uit twee rollen") % EPDM_MAX_WIDTH)
                result.append({
                    "dimensions": dimensions,
                    "surface": round(surface, 2),
                    "waste": round(waste, 2),
                    "waste_pct": round(waste / (length * width) * 100) if length * width else 0,
                    "margin": round(margin, 2),
                    "key": "%s-%s" % (section.id, index),
                    "section_id": section.id,
                    "name": (_("EPDM-doek %(name)s · %(index)s", name=name, index=index)
                             if len(sheets) > 1 else _("EPDM-doek %s") % name),
                    "length": round(length, 2),
                    "width": round(width, 2),
                    "area": round(length * width, 2),
                    "note": "; ".join(notes),
                })
        return result

    @api.model
    def _tectora_dimension_text(self, dimension):
        """'Lengte: 5,90 vlak + Z2 0,60 (opstand 0,20 + dakrand 0,30 + marge
        0,10) + naad 0,10 (overlap) = 7,30 → 7,35 m'"""
        def number(value):
            return ("%.2f" % value).replace(".", ",")

        parts = [_("%s vlak") % number(dimension["base"])]
        for end in dimension["ends"]:
            if end["seam"]:
                parts.append(_("naad %s (overlap)") % number(end["total"]))
                continue
            detail = []
            if end["upstand"]:
                detail.append(_("opstand %s") % number(end["upstand"]))
            if end["width"]:
                detail.append(_("dakrand %s") % number(end["width"]))
            detail.append(_("marge %s") % number(end["margin"]))
            parts.append("%s %s (%s)" % (end["label"], number(end["total"]), " + ".join(detail)))
        text = "%s: %s = %s" % (dimension["label"], " + ".join(parts), number(dimension["raw"]))
        if abs(dimension["size"] - dimension["raw"]) > 0.001:
            text += " → %s" % number(dimension["size"])
        return text + " m"

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
