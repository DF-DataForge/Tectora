# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

from odoo import api, models

_logger = logging.getLogger(__name__)

PRICE_BOOK = Path(__file__).parent.parent / "data" / "price_book.json"

# Core UoM external ids to try before creating our own, per price-book unit.
CORE_UOM_REFS = {
    "unit": "uom.product_uom_unit",
    "m": "uom.product_uom_meter",
    "m2": "uom.product_uom_square_meter",
    "day": "uom.product_uom_day",
    "hour": "uom.product_uom_hour",
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _tectora_import_price_book(self):
        """Load (or refresh) the price-book products, categories, units and
        pricelists from data/price_book.json. Idempotent: products are matched
        on their default_code, pricelist rules on (pricelist, product)."""
        if not PRICE_BOOK.exists():
            _logger.warning("tectora_products: %s missing, nothing imported", PRICE_BOOK)
            return
        data = json.loads(PRICE_BOOK.read_text(encoding="utf-8"))

        categories = self._tectora_load_categories(data["categories"])
        uoms = {key: self._tectora_get_uom(key, name) for key, name in data["uoms"].items()}
        pricelists = self._tectora_load_pricelists(data["pricelists"])
        tags = self._tectora_load_tags(data["products"])

        Product = self.env["product.template"]
        PricelistItem = self.env["product.pricelist.item"]
        created = updated = rules = 0
        for entry in data["products"]:
            values = {
                "name": entry["name"],
                "default_code": entry["code"],
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "list_price": entry["list_price"],
                "categ_id": categories[entry["category"]].id,
                "uom_id": uoms[entry["uom"]].id,
                "description_sale": entry["description"],
                "description": entry["note"] or False,
            }
            if "product_tag_ids" in Product._fields and entry["tags"]:
                values["product_tag_ids"] = [(6, 0, [tags[t].id for t in entry["tags"]])]
            product = Product.with_context(active_test=False).search(
                [("default_code", "=", entry["code"])], limit=1
            )
            if product:
                product.write(values)
                updated += 1
            else:
                product = Product.create(values)
                created += 1
            for project_type, price in entry["prices"].items():
                pricelist = pricelists[project_type]
                item = PricelistItem.search(
                    [
                        ("pricelist_id", "=", pricelist.id),
                        ("product_tmpl_id", "=", product.id),
                    ],
                    limit=1,
                )
                item_values = {
                    "pricelist_id": pricelist.id,
                    "product_tmpl_id": product.id,
                    "applied_on": "1_product",
                    "compute_price": "fixed",
                    "fixed_price": price,
                }
                if item:
                    item.write(item_values)
                else:
                    PricelistItem.create(item_values)
                rules += 1
        _logger.info(
            "tectora_products: price book imported (%s created, %s updated, "
            "%s pricelist rules)", created, updated, rules,
        )

    def _tectora_load_categories(self, entries):
        Category = self.env["product.category"]
        root = Category.search([("name", "=", "Dakwerken"), ("parent_id", "=", False)], limit=1)
        if not root:
            root = Category.create({"name": "Dakwerken"})
        result = {}
        for entry in entries:
            category = Category.search(
                [("name", "=", entry["name"]), ("parent_id", "=", root.id)], limit=1
            )
            if not category:
                category = Category.create({"name": entry["name"], "parent_id": root.id})
            result[entry["key"]] = category
        return result

    def _tectora_get_uom(self, key, name):
        """Resolve a unit: core external id first, then by name, else create it.

        Creation handles both the Odoo 19 flat UoM model (relative_uom_id/
        relative_factor) and the legacy category-based model.
        """
        ref = CORE_UOM_REFS.get(key)
        if ref:
            uom = self.env.ref(ref, raise_if_not_found=False)
            if uom:
                return uom
        Uom = self.env["uom.uom"].with_context(active_test=False)
        uom = Uom.search([("name", "=ilike", name)], limit=1)
        if uom:
            return uom
        values = {"name": name}
        unit = self.env.ref("uom.product_uom_unit")
        if "relative_uom_id" in Uom._fields:
            values.update({"relative_uom_id": unit.id, "relative_factor": 1.0})
        elif "category_id" in Uom._fields:
            values.update({
                "category_id": unit.category_id.id,
                "uom_type": "bigger",
                "factor_inv": 1.0,
            })
        return Uom.create(values)

    def _tectora_load_pricelists(self, entries):
        Pricelist = self.env["product.pricelist"]
        result = {}
        for project_type, name in entries.items():
            pricelist = Pricelist.search([("name", "=ilike", name)], limit=1)
            if not pricelist:
                pricelist = Pricelist.create({"name": name, "company_id": False})
            result[project_type] = pricelist
        return result

    def _tectora_load_tags(self, products):
        if "product_tag_ids" not in self.env["product.template"]._fields:
            return {}
        Tag = self.env["product.tag"]
        result = {}
        for entry in products:
            for tag_name in entry["tags"]:
                if tag_name not in result:
                    tag = Tag.search([("name", "=", tag_name)], limit=1)
                    result[tag_name] = tag or Tag.create({"name": tag_name})
        return result
