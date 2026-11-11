# -*- coding: utf-8 -*-
"""The quotation as the roof project builds it, in its standard segments:
Algemene werken, Veiligheid, per roof Afbouwwerken and Opbouwwerken, the
other chapters, Algemene nota's -- the same segments as the quotation itself
(sale.order._tectora_restructure). Shown on the roof project's Offerte tab
(the quotation builder) and next to the drawing.
"""
from odoo import _, api, models
from odoo.tools.misc import format_amount

STANDARD_KINDS = ("general", "safety", "demolition", "buildup", "notes")


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    def _tectora_quote_segments(self, with_empty=False):
        """The segments with their lines: per project line one row (it can be
        edited), the drawing's products one row per (product, coverage) with
        the parts of the drawing they come from, and the lines added on the
        quotation by hand. ``with_empty`` adds the standard segments that
        have nothing yet (to add products to)."""
        self.ensure_one()
        Roof = self.env["tectora.roof.project.roof"]
        Category = self.env["product.category"]
        currency = self.currency_id or self.env.company.currency_id
        coverage_labels = dict(
            self.env["tectora.roof.section.product"]._fields["coverage"].selection
        )
        roofs = self.roof_ids
        segments = {}

        def segment(kind, roof=Roof, chapter=Category):
            if kind in ("demolition", "buildup") and not roof and len(roofs) == 1:
                roof = roofs
            if kind not in ("demolition", "buildup"):
                roof = Roof
            key = self._tectora_segment_key(kind, roof, chapter)
            if key not in segments:
                segments[key] = {
                    "key": key,
                    "kind": kind,
                    "roof": roof,
                    "chapter": chapter,
                    "title": self._tectora_segment_title(kind, roof, chapter),
                    "roof_id": roof.id or False,
                    "lines": [],
                    "groups": {},
                    "total": 0.0,
                }
            return segments[key]

        def row(line, source):
            return {
                "key": "%s-%s" % (source, line.id),
                "source": source,
                "line_ids": [line.id],
                "direct_id": line.id if source == "project" else False,
                "product_id": line.product_id.id,
                "product": line.product_id.display_name,
                "coverage": line.coverage,
                "coverage_label": coverage_labels.get(line.coverage, line.coverage or ""),
                "uom": line.uom_id.name or "",
                "price": line.price_unit,
                "quantity": 0.0,
                "subtotal": 0.0,
                "targets": [],
                "project_line": source == "project",
            }

        # The drawing's lines, per (product, coverage) within a segment.
        def add_drawn(line, target, target_kind):
            kind, chapter = self._tectora_product_segment(line.product_id)
            data = segment(kind or "other", line._tectora_roof(), chapter)
            group_key = (line.product_id.id, line.coverage)
            entry = data["groups"].get(group_key)
            if not entry:
                entry = data["groups"][group_key] = row(line, "drawing")
                entry["key"] = "drawing-%s-%s-%s" % (data["key"], line.product_id.id, line.coverage)
                data["lines"].append(entry)
            else:
                entry["line_ids"].append(line.id)
            entry["quantity"] += line.quantity
            entry["subtotal"] += line.price_subtotal
            data["total"] += line.price_subtotal
            if target.canvas_ref:
                entry["targets"].append({
                    "canvas_ref": target.canvas_ref,
                    "kind": target_kind,
                    "name": target.name or "",
                    "coverage": line.coverage,
                    "edge_index": line.edge_index or 0,
                })

        for section in self.section_ids:
            for line in section.product_line_ids:
                if line.product_id:
                    add_drawn(line, section, "section")
        for roof_object in self.roof_object_ids:
            for line in roof_object.product_line_ids:
                if line.product_id:
                    add_drawn(line, roof_object, "object")

        # Project lines (a product the drawing prices is priced there).
        for line in self.direct_line_ids:
            if not line.product_id or line.product_id in self._tectora_measured_products(line.roof_id):
                continue
            kind, chapter = self._tectora_product_segment(line.product_id)
            data = segment(kind or "other", line.roof_id, chapter)
            entry = row(line, "project")
            entry["quantity"] = line.quantity
            entry["subtotal"] = line.price_subtotal
            data["lines"].append(entry)
            data["total"] += line.price_subtotal

        # Lines added on the quotation by hand (not mirrored).
        order = self.sale_order_id
        if order:
            for line in order.order_line.sorted(lambda l: (l.sequence, l.id)):
                if (line.display_type or not line.product_id or line.roof_line_id
                        or line.roof_measurement_line):
                    continue
                kind, chapter = self._tectora_product_segment(line.product_id)
                data = segment(kind or "other", line.tectora_roof_id, chapter)
                data["lines"].append({
                    "key": "order-%s" % line.id,
                    "source": "order",
                    "line_ids": [line.id],
                    "direct_id": False,
                    "product_id": line.product_id.id,
                    "product": (line.name or "").split("\n")[0] or line.product_id.display_name,
                    "coverage": "general",
                    "coverage_label": _("Op de offerte"),
                    "uom": line.product_uom_id.name or "",
                    "price": line.price_unit,
                    "quantity": line.product_uom_qty,
                    "subtotal": line.price_subtotal,
                    "targets": [],
                    "project_line": True,
                })
                data["total"] += line.price_subtotal

        if with_empty:
            segment("general")
            segment("safety")
            for roof in (roofs or [Roof]):
                segment("demolition", roof)
                segment("buildup", roof)
            segment("notes")

        result = sorted(segments.values(), key=lambda s: self._tectora_segment_rank(
            s["kind"], s["roof"], s["chapter"]
        ))
        for data in result:
            data.pop("groups")
            data["rank"] = list(self._tectora_segment_rank(data["kind"], data["roof"], data["chapter"]))
            data["roof_name"] = data.pop("roof")._subsection_name() if data["roof_id"] else ""
            data["chapter_id"] = data.pop("chapter").id or False
            data["total_display"] = format_amount(self.env, data["total"], currency)
            for entry in data["lines"]:
                entry["quantity"] = round(entry["quantity"], 2)
                entry["subtotal_display"] = format_amount(self.env, entry["subtotal"], currency)
                entry["price_display"] = format_amount(self.env, entry["price"], currency)
            data["lines"].sort(key=lambda e: (e["source"] != "project" and e["source"] != "drawing",
                                              e["source"] == "drawing", e["product"].lower()))
        return result

    def _tectora_quote_header(self, segments):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        order = self.sale_order_id
        total = sum(s["total"] for s in segments)
        return {
            "total": total,
            "total_display": format_amount(self.env, total, currency),
            "order": order.name if order else "",
            "order_id": order.id if order else False,
            "follows": bool(order and order.tectora_follow_measurement),
            "locked": bool(order and order.tectora_locked),
        }

    def tectora_get_quote_preview(self):
        """The quotation next to the drawing: the segments of the roof on the
        drawing (with several roofs) and those of the whole project, each
        line with the parts of the drawing it comes from."""
        self.ensure_one()
        roof = self.active_roof_id
        segments = [
            s for s in self._tectora_quote_segments()
            if not (len(self.roof_ids) > 1 and s["kind"] in ("demolition", "buildup")
                    and s["roof_id"] and s["roof_id"] != roof.id)
        ]
        chapters = [{
            "key": s["key"],
            "label": s["title"],
            "total": s["total"],
            "total_display": s["total_display"],
            "lines": [dict(line, line_ids=line["line_ids"]) for line in s["lines"]],
        } for s in segments if s["lines"]]
        result = self._tectora_quote_header(segments)
        result.update({
            "roof": roof._subsection_name() if roof and len(self.roof_ids) > 1 else "",
            "chapters": chapters,
            "manual": [],
            "manual_total_display": "",
            "grand_total_display": result["total_display"],
        })
        return result

    # ------------------------------------------------------------- builder
    @api.model
    def _tectora_segment_categories(self, kind, chapter_id=False):
        """The categories a segment's products are added from: the chapters
        of that kind (with their sub-categories)."""
        Category = self.env["product.category"]
        if kind == "other" and chapter_id:
            return Category.search([("id", "child_of", chapter_id)]).ids
        chapters = Category.search([("name", "=like", "__.%")]).filtered(
            lambda c: self._tectora_segment_kind(c.name) == kind
        )
        if not chapters:
            return []
        return Category.search([("id", "child_of", chapters.ids)]).ids

    def tectora_get_quote_builder(self):
        """The Offerte tab: every standard segment (also the empty ones, to
        add products to), with the categories to add from."""
        self.ensure_one()
        segments = self._tectora_quote_segments(with_empty=True)
        for data in segments:
            data["category_ids"] = self._tectora_segment_categories(data["kind"], data["chapter_id"])
        result = self._tectora_quote_header(segments)
        result.update({
            "segments": segments,
            "notes": self.quote_notes or "",
            "roofs": [{"id": r.id, "name": r._subsection_name()} for r in self.roof_ids],
        })
        return result

    def tectora_builder_add(self, segment_key, product_ids):
        """Add products to a segment as project lines (of its roof)."""
        self.ensure_one()
        roof_id = False
        kind, _sep, rest = (segment_key or "").partition(":")
        if kind in ("demolition", "buildup") and rest and rest != "0":
            roof = self.env["tectora.roof.project.roof"].browse(int(rest)).exists()
            if roof and roof.project_id == self:
                roof_id = roof.id
        existing = self.direct_line_ids.filtered(lambda l: (l.roof_id.id or False) == roof_id)
        values = [
            {"project_direct_id": self.id, "product_id": product_id, "roof_id": roof_id}
            for product_id in product_ids
            if product_id not in existing.product_id.ids
        ]
        if values:
            self.env["tectora.roof.section.product"].create(values)
        return len(values)
