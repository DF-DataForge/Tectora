# -*- coding: utf-8 -*-
"""The demolition (afbouw) of a roof surface or side, from the drawing.

The product picker of a surface or a side offers an "Afbouw" tab: the
demolition works of chapter 03 (Afbraakwerken plat dak) that fit it -- per
m² for a surface (dakbedekking, isolatie, dakvloer, ballast ...), per m for
a side (dakranden, solins, muurkappen ...) -- grouped by what is removed, to
tick. The ticked works are on the surface or side, the unticked ones not.
"""
from odoo import api, models


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    @api.model
    def _tectora_demolition_products(self):
        Category = self.env["product.category"]
        chapters = Category.search([("name", "=like", "__.%")]).filtered(
            lambda c: self._tectora_segment_kind(c.name) == "demolition"
        )
        if not chapters:
            return self.env["product.product"], chapters
        products = self.env["product.product"].search([
            ("sale_ok", "=", True), ("categ_id", "child_of", chapters.ids),
        ])
        return products, chapters

    def tectora_get_demolition_options(self, scope):
        """The demolition works for a surface (``scope`` "surface": per m²)
        or a side ("edge": per m), grouped by what is removed."""
        self.ensure_one()
        products, chapters = self._tectora_demolition_products()
        Line = self.env["tectora.roof.section.product"]
        wanted = "surface" if scope == "surface" else "edges"
        result = []
        for product in products:
            if Line._coverage_from_product(product) != wanted:
                continue
            group = product.categ_id.name if product.categ_id not in chapters else "Algemeen"
            result.append({
                "id": product.id,
                "name": product.display_name,
                "code": product.default_code or "",
                "price": product.lst_price,
                "uom": product.uom_id.name or "",
                "group": group,
            })
        result.sort(key=lambda r: (r["group"] == "Algemeen", r["group"], r["name"]))
        return result

    def tectora_apply_selection(self, items, coverage, product_ids, option_ids, link_field="section_id"):
        """Of the products ``option_ids``, put exactly ``product_ids`` on the
        targets ``items`` ([{record_id, side, quantity}]): the missing ones
        are added, the others of the options removed. Returns the counts."""
        self.ensure_one()
        if link_field not in ("section_id", "object_id"):
            link_field = "section_id"
        Line = self.env["tectora.roof.section.product"]
        Target = self.env["tectora.roof.section" if link_field == "section_id" else "tectora.roof.object"]
        wanted = set(product_ids or [])
        options = set(option_ids or []) | wanted
        added = removed = 0
        for item in items or []:
            target = Target.browse(int(item.get("record_id") or 0)).exists()
            if not target or target.project_id != self:
                continue
            side = int(item.get("side") or 0)
            existing = Line.search([
                (link_field, "=", target.id), ("coverage", "=", coverage),
                ("edge_index", "=", side), ("product_id", "in", list(options)),
            ])
            stale = existing.filtered(lambda l: l.product_id.id not in wanted)
            removed += len(stale)
            stale.unlink()
            have = set(existing.exists().product_id.ids)
            values = [{
                link_field: target.id,
                "product_id": product_id,
                "coverage": coverage,
                "edge_index": side,
                "quantity": float(item.get("quantity") or 0.0) or 1.0,
            } for product_id in wanted - have]
            if values:
                Line.create(values)
                added += len(values)
        return {"added": added, "removed": removed}
