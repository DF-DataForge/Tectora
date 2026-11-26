# -*- coding: utf-8 -*-
"""The finish of a roof surface's sides (Randafwerking), from the drawing.

The product picker of a side offers a "Randafwerking" tab: a free side gets
a roof edge (dakrandprofiel or kraal: type, height, finish), a side against
a wall, the neighbours' roof or a gutter a connection (aansluiting). Each
has its own products (02. Dakranden, 04. Opbouwwerken plat dak/Aansluitingen).
A roof edge brings its corners: where two sides with the same edge meet, the
matching inner or outer corner piece (binnenhoek / buitenhoek of the same
type, height and finish) is put on that corner.
"""
import re

from odoo import _, api, models

# The edge types, in the order the dialog lists them: (label, pattern).
EDGE_FAMILIES = (
    (r"2-delige (alu )?dakrand", "2-delige alu dakrand"),
    (r"enkelvoudige dakrand", "Enkelvoudige dakrand"),
    (r"zinken kra(al|len)", "Zinken kraal"),
    (r"2-delige alu(minium)? kra(al|len)", "2-delige alu kraal (Iconik)"),
    (r"enkelvoudige alu(minium)? kra(al|len)", "Enkelvoudige alu kraal"),
)

FINISHES = (
    ("ral 9005", "RAL 9005 structuurlak"),
    ("ral naar keuze", "RAL naar keuze"),
    ("ral stock", "RAL stock"),
    ("geanodiseerd", "Geanodiseerd"),
    ("brut", "Brut"),
    ("naturel", "Naturel zink"),
    ("quartz", "Quartz zink"),
    ("anthra", "Anthra zink"),
)

# Connections, grouped by what the side meets.
CONNECTION_GROUPS = (
    (r"buren", "Dak van de buren"),
    (r"goot", "Goot"),
    (r"dekpannen|hellend dak|onderdak", "Hellend dak"),
    (r"dorpel|schuifraam|raam of deur", "Dorpel / raam"),
    (r"onderkapping", "Onderkapping"),
    (r"gevelbekleding|gevelafwerking|volkern|crepi|sidings", "Gevelbekleding"),
    (r"dekste|muurkap|c-profiel", "Deksteen / muurkap"),
    (r"solin|wandaansluit|gevel|slabbe|lood|metser", "Muur / gevel"),
    (r"", "Andere aansluitingen"),
)


def _clean(name):
    return re.sub(r"\s+", " ", (name or "")).strip()


def edge_info(name):
    """Type, height and finish of a roof edge (or its corner) from the
    catalogue's name: "Leveren en plaatsen van de enkelvoudige
    dakrandprofielen hoogte: 60mm in RAL naar keuze"."""
    lowered = _clean(name).lower()
    family = ""
    for pattern, label in EDGE_FAMILIES:
        if re.search(pattern, lowered):
            family = label
            break
    height = re.search(r"hoogte:\s*(\d+)\s*mm", lowered)
    finish = ""
    for word, label in FINISHES:
        if word in lowered:
            finish = label
            break
    if "druiplijst" in lowered:
        finish = ("%s + druiplijst" % finish) if finish else "Met druiplijst"
    corner = "inner" if "binnenhoek" in lowered else "outer" if "buitenhoek" in lowered else ""
    return {
        "type": family,
        "height": int(height.group(1)) if height else 0,
        "height_label": "%s mm" % height.group(1) if height else "",
        "finish": finish,
        "corner": corner,
        "end": "eindstuk" in lowered,
    }


def corner_kind(points, index):
    """'inner' or 'outer' for the corner at points[index] (mirror of the
    drawing's isInnerCorner)."""
    n = len(points)
    ax, ay = points[(index - 1) % n]
    px, py = points[index]
    bx, by = points[(index + 1) % n]
    cross = (px - ax) * (by - py) - (py - ay) * (bx - px)
    if cross == 0:
        return "outer"
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    orientation = 1 if area >= 0 else -1
    return "inner" if (1 if cross > 0 else -1) != orientation else "outer"


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    # ------------------------------------------------------------- products
    @api.model
    def _tectora_chapter_products(self, category_names, name_words=()):
        """Sold products in the categories named ``category_names`` (and
        their sub-categories) or named with one of ``name_words``."""
        categories = self.env["product.category"].search([("name", "in", list(category_names))])
        alternatives = [[("name", "ilike", word)] for word in name_words]
        if categories:
            alternatives.append([("categ_id", "child_of", categories.ids)])
        if not alternatives:
            return self.env["product.product"]
        domain = [("sale_ok", "=", True)]
        domain += ["|"] * (len(alternatives) - 1) + [t for alt in alternatives for t in alt]
        return self.env["product.product"].search(domain).filtered(
            lambda p: not re.search(r"verwijder|afbraak|demonteren", (p.name or "").lower())
        )

    @api.model
    def _tectora_edge_products(self):
        """(profiles per metre, corner and end pieces) of the roof edges."""
        products = self._tectora_chapter_products(
            ["02. Dakranden", "Dakrandprofielen", "Kralen", "Hoeken & eindstukken"]
        )
        pieces = products.filtered(
            lambda p: re.search(r"binnenhoek|buitenhoek|eindstuk", (p.name or "").lower())
        )
        return products - pieces, pieces

    @api.model
    def _tectora_connection_products(self):
        products = self._tectora_chapter_products(
            ["Aansluitingen"],
            ["aansluiting", "solins", "wandaansluit", "slabben", "onderkapping", "dorpel",
             "dekstenen", "gevelbekleding"],
        )
        return products.filtered(
            lambda p: not re.search(
                r"binnenhoek|buitenhoek|eindstuk|schoorsteen|schouw", (p.name or "").lower()
            )
        )

    @api.model
    def _tectora_product_row(self, product):
        return {
            "id": product.id,
            "name": product.display_name,
            "code": product.default_code or "",
            "price": product.lst_price,
            "uom": product.uom_id.name or "",
        }

    def tectora_get_edge_options(self):
        """The products for the "Randafwerking" dialog: the roof edges by
        type, height and finish, and the connections by what they meet."""
        self.ensure_one()
        profiles, _pieces = self._tectora_edge_products()
        edges = []
        for product in profiles:
            row = self._tectora_product_row(product)
            row.update(edge_info(product.name))
            row["type"] = row["type"] or _clean(product.name)
            edges.append(row)
        edges.sort(key=lambda r: (
            [label for _p, label in EDGE_FAMILIES].index(r["type"])
            if r["type"] in [label for _p, label in EDGE_FAMILIES] else 99,
            r["type"], r["height"], r["finish"], r["name"],
        ))
        connections = []
        for product in self._tectora_connection_products():
            row = self._tectora_product_row(product)
            lowered = (product.name or "").lower()
            row["group"] = next(label for pattern, label in CONNECTION_GROUPS
                                if not pattern or re.search(pattern, lowered))
            connections.append(row)
        group_order = [label for _p, label in CONNECTION_GROUPS]
        connections.sort(key=lambda r: (group_order.index(r["group"]), r["name"]))
        return {"edges": edges, "connections": connections}

    # ---------------------------------------------------------------- apply
    @api.model
    def _tectora_matching_corner(self, profile, kind, pieces):
        """The inner or outer corner piece of the same type, height and
        finish as ``profile``, or an empty recordset."""
        wanted = edge_info(profile.name)
        candidates = [
            (piece, edge_info(piece.name)) for piece in pieces
        ]
        candidates = [
            (piece, info) for piece, info in candidates
            if info["corner"] == kind and info["type"] == wanted["type"]
            and info["height"] == wanted["height"]
        ]
        for piece, info in candidates:
            if info["finish"] == wanted["finish"]:
                return piece
        # A corner named without its finish ("buitenhoek ... Iconik in RAL")
        # serves every finish of its type.
        for piece, info in candidates:
            if not info["finish"]:
                return piece
        return pieces.browse()

    def _tectora_section_points(self, section):
        source = self
        if section.roof_id and section.roof_id != self.active_roof_id:
            source = section.roof_id
        for shape in self._parse_canvas_shapes(source.canvas_data or ""):
            if shape["id"] == section.canvas_ref and shape["kind"] == "section":
                return shape["points"]
        return []

    def tectora_apply_edges(self, items, kind, product_id, corners=True, dry_run=False):
        """Put the finish on the sides ``items`` ([{section_id, side (1-based),
        quantity (m)}]): ``kind`` "edge" (a roof edge) or "connection". The
        side's earlier roof edge or connections are replaced. A side takes
        one roof edge, or one or more connections (``product_id`` a list: a
        wall profile and the connection to the cladding above it, a sill and
        its flashing). A roof edge also gets its corners where two sides with
        that edge meet. With ``dry_run`` nothing is written: the corners it
        would take are returned."""
        self.ensure_one()
        Section = self.env["tectora.roof.section"]
        Line = self.env["tectora.roof.section.product"]
        product_ids = product_id if isinstance(product_id, (list, tuple)) else [product_id]
        chosen = self.env["product.product"].browse(
            [int(pid) for pid in product_ids if pid]
        ).exists()
        # The roof edge the corners follow: the one product of an edge.
        product = chosen[:1]
        profiles, pieces = self._tectora_edge_products()
        connections = self._tectora_connection_products()
        finishes = profiles | connections
        by_section = {}
        for item in items or []:
            section = Section.browse(int(item.get("section_id") or 0)).exists()
            side = int(item.get("side") or 0)
            if section and section.project_id == self and side > 0:
                by_section.setdefault(section, {})[side] = float(item.get("quantity") or 0.0)
        result = {"lines": 0, "corners": {"inner": 0, "outer": 0}, "missing": [],
                  "inner_product": "", "outer_product": "", "inner_price": 0.0, "outer_price": 0.0}
        if not product:
            return result
        for section, sides in by_section.items():
            if not dry_run:
                section.product_line_ids.filtered(
                    lambda l: l.coverage == "edges" and l.edge_index in sides
                    and l.product_id in finishes
                ).unlink()
                for side, quantity in sorted(sides.items()):
                    for finish in (chosen if kind == "connection" else product):
                        Line.create({
                            "section_id": section.id,
                            "product_id": finish.id,
                            "coverage": "edges",
                            "edge_index": side,
                            "quantity": quantity or 1.0,
                        })
                        result["lines"] += 1
            points = self._tectora_section_points(section)
            n = len(points)
            if n < 3:
                continue
            if not dry_run:
                # A corner piece stays only where two sides with a roof edge
                # still meet.
                with_edge = set(section.product_line_ids.filtered(
                    lambda l: l.coverage == "edges" and l.product_id in profiles
                ).mapped("edge_index"))
                section.product_line_ids.filtered(
                    lambda l: l.coverage == "corners" and l.product_id in pieces
                    and l.edge_index
                    and not ((l.edge_index - 1 or n) in with_edge and l.edge_index in with_edge)
                ).unlink()
            if kind != "edge" or not corners:
                continue
            # The sides with this edge: the ones now chosen and those that
            # already had it.
            edged = set(sides) | set(section.product_line_ids.filtered(
                lambda l: l.coverage == "edges" and l.product_id == product
            ).mapped("edge_index"))
            for corner in range(1, n + 1):
                before = corner - 1 or n
                if before not in edged or corner not in edged:
                    continue
                if before not in sides and corner not in sides:
                    continue  # both sides were done before: corner as it is
                corner_type = corner_kind(points, corner - 1)
                piece = self._tectora_matching_corner(product, corner_type, pieces)
                if not piece:
                    label = _("binnenhoek") if corner_type == "inner" else _("buitenhoek")
                    if label not in result["missing"]:
                        result["missing"].append(label)
                    continue
                result["corners"][corner_type] += 1
                result["%s_product" % corner_type] = piece.display_name
                result["%s_price" % corner_type] = piece.lst_price
                if dry_run:
                    continue
                section.product_line_ids.filtered(
                    lambda l: l.coverage == "corners" and l.edge_index == corner
                    and l.product_id in pieces
                ).unlink()
                Line.create({
                    "section_id": section.id,
                    "product_id": piece.id,
                    "coverage": "corners",
                    "edge_index": corner,
                    "quantity": 1.0,
                })
        return result

    # ------------------------------------------------------------ split side
    def tectora_split_side(self, section_id, side, length_first, length_second):
        """A side of a surface was cut in two on the drawing (a point put on
        it: the wall, then the window): side ``side`` (1-based) is now
        ``length_first`` m long and the new side after it ``length_second`` m;
        every later side and corner moved up one.

        The products follow: those of later sides and corners move with
        them, those of the cut side stay on its first part with the new
        length and are copied onto the second part, so both parts start from
        what the whole side had and each can then be given its own."""
        self.ensure_one()
        section = self.env["tectora.roof.section"].browse(int(section_id or 0)).exists()
        side = int(side or 0)
        if not section or section.project_id != self or side < 1:
            return False
        Line = self.env["tectora.roof.section.product"].with_context(tectora_sync=True)
        lines = section.product_line_ids.with_context(tectora_sync=True)
        # Highest first, so no two lines ever share a number on the way.
        for line in lines.filtered(lambda l: l.edge_index > side).sorted(
            lambda l: -l.edge_index
        ):
            line.edge_index = line.edge_index + 1
        copies = []
        for line in lines.filtered(lambda l: l.edge_index == side and l.coverage == "edges"):
            fixed = line.quantity_mode == "fixed"
            factor = line.quantity_factor or 1.0
            if not fixed:
                line.quantity = round(float(length_first or 0.0) * factor, 2) or 1.0
            copies.append({
                "section_id": section.id,
                "product_id": line.product_id.id,
                "coverage": "edges",
                "edge_index": side + 1,
                "quantity_mode": line.quantity_mode,
                "quantity_factor": line.quantity_factor,
                "is_conditional": line.is_conditional,
                "quantity": line.quantity if fixed
                else (round(float(length_second or 0.0) * factor, 2) or 1.0),
            })
        if copies:
            Line.create(copies)
        self._tectora_mirror_to_order()
        return True

    def tectora_merge_sides(self, section_id, kept, dropped, length):
        """The reverse of tectora_split_side: the point between two sides in
        line was taken off the drawing, so side ``dropped`` (1-based) is gone
        into side ``kept``, now ``length`` m long, and every later side and
        corner moved down one.

        The products follow: what was on the dropped side goes onto the kept
        one (a product both had stays once), with the whole length; a corner
        piece on the point that is gone is removed; the later sides and
        corners move with their numbers."""
        self.ensure_one()
        section = self.env["tectora.roof.section"].browse(int(section_id or 0)).exists()
        kept, dropped = int(kept or 0), int(dropped or 0)
        if not section or section.project_id != self or kept < 1 or dropped < 1 or kept == dropped:
            return False
        lines = section.product_line_ids.with_context(tectora_sync=True)
        # The corner on the point that is gone.
        lines.filtered(lambda l: l.edge_index == dropped and l.coverage == "corners").unlink()
        lines = lines.exists()
        on_kept = lines.filtered(lambda l: l.edge_index == kept and l.coverage == "edges")
        have = on_kept.product_id
        for line in lines.filtered(lambda l: l.edge_index == dropped and l.coverage == "edges"):
            if line.product_id in have:
                line.unlink()
            else:
                line.edge_index = kept
                have |= line.product_id
                on_kept |= line
        for line in on_kept.exists():
            if line.quantity_mode != "fixed":
                line.quantity = round(float(length or 0.0) * (line.quantity_factor or 1.0), 2) or 1.0
        # Lowest first, so no two lines ever share a number on the way.
        for line in section.product_line_ids.with_context(tectora_sync=True).filtered(
            lambda l: l.edge_index > dropped
        ).sorted("edge_index"):
            line.edge_index = line.edge_index - 1
        self._tectora_mirror_to_order()
        return True
