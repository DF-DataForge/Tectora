# -*- coding: utf-8 -*-
"""The demolition (afbouw) of a roof surface or side, from the drawing.

The product picker of a surface or a side offers an "Afbouw" tab: the
demolition works of chapter 03 (Afbraakwerken plat dak) that fit it -- per
m² for a surface (dakbedekking, isolatie, dakvloer, ballast ...), per m for
a side (dakranden, solins, muurkappen ...) -- grouped by what is removed, to
tick. The ticked works are on the surface or side, the unticked ones not.
"""
import re

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

    def tectora_apply_selection(self, items, coverage, product_ids, option_ids,
                                link_field="section_id", factors=None):
        """Of the products ``option_ids``, put exactly ``product_ids`` on the
        targets ``items`` ([{record_id, side, quantity}]): the missing ones
        are added, the others of the options removed. ``factors`` ({product
        id: factor}) sets how many of a product go per unit of the target's
        measure (8 tile supports per m², 0.12 for 12 % cutting waste).
        Returns the counts."""
        self.ensure_one()
        factors = {int(key): float(value or 0.0) for key, value in (factors or {}).items()}
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
            kept = existing.exists()
            have = set(kept.product_id.ids)
            for line in kept:
                factor = factors.get(line.product_id.id)
                if factor and factor != (line.quantity_factor or 1.0):
                    line.quantity_factor = factor
            measure = float(item.get("quantity") or 0.0) or 1.0
            values = [{
                link_field: target.id,
                "product_id": product_id,
                "coverage": coverage,
                "edge_index": side,
                "quantity_factor": factors.get(product_id) or 1.0,
                # Counted targets (a tapbuis: 1 piece) take the factor as
                # their quantity; measured ones are computed from it.
                "quantity": measure * (factors.get(product_id) or 1.0),
            } for product_id in wanted - have]
            if values:
                Line.create(values)
                added += len(values)
        return {"added": added, "removed": removed}

    # ------------------------------------------- terrace floor and tapbuis
    # Two more tick lists of the picker, each with how many go per unit:
    # the terrace floor on a surface (chapter "Terrasvloer": tile supports
    # per m², tiles, cutting waste) and the works on a tapbuis (remove it,
    # the new one by diameter, its leaf guard).
    TERRACE_SUPPORTS_PER_M2 = 8.0
    TERRACE_WASTE = 0.12

    @api.model
    def _tectora_option_row(self, product, group, factor=1.0):
        return {
            "id": product.id,
            "name": product.display_name,
            "code": product.default_code or "",
            "price": product.lst_price,
            "uom": product.uom_id.name or "",
            "group": group,
            "factor": factor,
        }

    def tectora_get_terrace_options(self):
        """The products of the terrace floor, with the factor each starts
        from: 8 supports per m², 12 % cutting waste, else the m² itself."""
        self.ensure_one()
        chapters = self.env["product.category"].search([("name", "ilike", "terras")]).filtered(
            lambda c: self._tectora_segment_kind(c.complete_name or c.name) != "demolition"
        )
        products = self.env["product.product"].search([
            ("sale_ok", "=", True),
            "|", ("categ_id", "child_of", chapters.ids),
            "|", ("name", "ilike", "tegeldrager"), ("name", "ilike", "snijafval"),
        ]) if chapters else self.env["product.product"].search([
            ("sale_ok", "=", True),
            "|", "|", ("name", "ilike", "tegeldrager"), ("name", "ilike", "snijafval"),
            ("name", "ilike", "terras"),
        ])
        rows = []
        for product in products:
            lowered = (product.name or "").lower()
            if re.search(r"verwijder|afbraak|demonteren", lowered):
                continue
            if "tegeldrager" in lowered:
                rows.append(self._tectora_option_row(
                    product, "Tegeldragers (stuks per m²)", self.TERRACE_SUPPORTS_PER_M2))
            elif "snijafval" in lowered or "snijverlies" in lowered:
                rows.append(self._tectora_option_row(
                    product, "Snijafval (deel van de m²)", self.TERRACE_WASTE))
            else:
                rows.append(self._tectora_option_row(product, "Terrasvloer"))
        order = ["Tegeldragers (stuks per m²)", "Terrasvloer", "Snijafval (deel van de m²)"]
        rows.sort(key=lambda r: (order.index(r["group"]), r["name"]))
        return rows

    def tectora_get_drain_options(self):
        """The works on a tapbuis: removing the old one, the new one, its
        leaf guard -- each one piece per tapbuis."""
        self.ensure_one()
        products = self.env["product.product"].search([
            ("sale_ok", "=", True),
            "|", "|", "|", ("name", "ilike", "tapbuis"), ("name", "ilike", "bolrooster"),
            ("name", "ilike", "bladvanger"), ("name", "ilike", "spuwer"),
        ])
        rows = []
        for product in products:
            lowered = (product.name or "").lower()
            if re.search(r"verwijder|afbraak|demonteren", lowered):
                group = "Verwijderen"
            elif "bolrooster" in lowered or "bladvanger" in lowered:
                group = "Bolrooster / bladvanger"
            elif re.search(r"leveren en plaatsen van (de |het )?(pe-|pp-)?tapbuis|tapbuis (pp|pe)", lowered):
                group = "Nieuwe tapbuis"
            else:
                group = "Andere werken aan de tapbuis"
            rows.append(self._tectora_option_row(product, group))
        order = ["Verwijderen", "Nieuwe tapbuis", "Bolrooster / bladvanger",
                 "Andere werken aan de tapbuis"]
        rows.sort(key=lambda r: (order.index(r["group"]), r["name"]))
        return rows
