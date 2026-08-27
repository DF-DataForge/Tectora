# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

from odoo import api, models

from . import catalog_rules

_logger = logging.getLogger(__name__)

# Root of the works category tree; every chapter hangs under it.
DEFAULT_ROOT_CATEGORY = "Dakwerken"
PRICE_BOOK = Path(__file__).parent.parent / "data" / "price_book.json"
PRODUCT_CATALOG = Path(__file__).parent.parent / "data" / "product_catalog.json"

# Core UoM external ids to try before creating our own, per price-book unit.
CORE_UOM_REFS = {
    "unit": "uom.product_uom_unit",
    "m": "uom.product_uom_meter",
    "m2": "uom.product_uom_square_meter",
    "day": "uom.product_uom_day",
    "hour": "uom.product_uom_hour",
    "kg": "uom.product_uom_kgm",
}
CATALOG_UOM_NAMES = {
    "unit": "Stuk",
    "m": "m",
    "m2": "m²",
    "kg": "kg",
    "hour": "Uur",
    "day": "Dag",
    "forfait": "Forfait",
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
                "categ_id": self._tectora_refined_category(
                    entry["category"], entry["name"], categories
                ).id,
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

    # ------------------------------------------------------- product catalog
    @api.model
    def _tectora_apply_catalog(self, entries, options=None):
        """Create/update products from catalogue entries.

        Shared by the shipped JSON catalogue and the import wizard. Every
        entry carries a ``category_path`` (resolved under the root category),
        a unit key, prices, the vendor and whether it is a service (a sales/
        works item) or goods (a purchasable, storable material).

        Matching is on the internal reference (``default_code``); entries
        without one are matched on name inside their category, so a file
        without references still imports without creating duplicates.
        """
        options = options or {}
        root_name = options.get("root_category") or DEFAULT_ROOT_CATEGORY
        sale_ok_goods = options.get("sale_ok_goods", True)
        Product = self.env["product.template"]
        SupplierInfo = self.env["product.supplierinfo"]

        uoms = {}
        categories = {}
        vendors = {}
        tags = self._tectora_load_tags(entries)
        counters = {"created": 0, "updated": 0, "vendor_lines": 0}

        for entry in entries:
            path = entry["category_path"]
            if path not in categories:
                categories[path] = self._tectora_resolve_category(path, root_name)
            key = entry["uom"]
            if key not in uoms:
                uoms[key] = self._tectora_get_uom(
                    key, catalog_rules.UOM_NAMES.get(key, "Stuk")
                )
            values = {
                "name": entry["name"],
                "list_price": entry["list_price"],
                "categ_id": categories[path].id,
                "uom_id": uoms[key].id,
                "description_sale": entry.get("description") or False,
            }
            if entry.get("code"):
                values["default_code"] = entry["code"]
            if entry["is_service"]:
                # Sales/works item: quoted, not stocked.
                values.update({"type": "service", "sale_ok": True,
                               "purchase_ok": False})
            else:
                # Raw material: purchased and stocked.
                values.update({"type": "consu", "sale_ok": sale_ok_goods,
                               "purchase_ok": True})
                if "is_storable" in Product._fields:
                    values["is_storable"] = True
            if entry.get("barcode"):
                values["barcode"] = entry["barcode"]
            if entry.get("weight") and "weight" in Product._fields:
                values["weight"] = entry["weight"]
            if "product_tag_ids" in Product._fields and entry.get("tags"):
                values["product_tag_ids"] = [
                    (6, 0, [tags[tag].id for tag in entry["tags"]])
                ]

            product = Product.browse()
            if entry.get("code"):
                product = Product.with_context(active_test=False).search(
                    [("default_code", "=", entry["code"])], limit=1
                )
            if not product:
                product = Product.with_context(active_test=False).search(
                    [
                        ("name", "=", entry["name"]),
                        ("categ_id", "=", categories[path].id),
                    ],
                    limit=1,
                )
            if product:
                product.write(values)
                counters["updated"] += 1
            else:
                product = Product.create(values)
                counters["created"] += 1
            if entry.get("standard_price"):
                product.standard_price = entry["standard_price"]

            supplier_name = entry.get("supplier")
            if not supplier_name:
                continue
            if supplier_name not in vendors:
                vendors.update(self._tectora_load_vendors([supplier_name]))
            vendor = vendors[supplier_name]
            line_values = {
                "partner_id": vendor.id,
                "product_tmpl_id": product.id,
                "price": entry.get("standard_price") or 0.0,
                "product_code": entry.get("supplier_code") or False,
            }
            line = SupplierInfo.search(
                [("partner_id", "=", vendor.id),
                 ("product_tmpl_id", "=", product.id)],
                limit=1,
            )
            if line:
                line.write(line_values)
            else:
                SupplierInfo.create(line_values)
            counters["vendor_lines"] += 1
        return counters

    @api.model
    def _tectora_ensure_category_tree(self, root_name=None):
        """Create every chapter and sub-category of the works structure.

        The imports create only the categories their products need, so the
        chapters nobody sells from yet (07. Oversteken, 09. Worst case
        scenario, ...) would never appear -- and a category that does not exist
        cannot be filed into by hand either. Idempotent.
        """
        root_name = root_name or DEFAULT_ROOT_CATEGORY
        created = 0
        before = self.env["product.category"].search_count([])
        for path in catalog_rules.CATEGORY_PATHS.values():
            self._tectora_resolve_category(path, root_name)
        created = self.env["product.category"].search_count([]) - before
        _logger.info("tectora_products: %s categories added to the tree", created)
        return created

    @api.model
    def _tectora_recategorise(self, entries=None, root_name=None):
        """Re-file existing products on the current category rules.

        Used when the rules gain a sub-category: the products are already
        there, only their category has to follow. Products whose category was
        changed by hand outside the works tree are left alone.
        """
        root_name = root_name or DEFAULT_ROOT_CATEGORY
        wanted = {}
        if entries is None:
            entries = []
            if PRODUCT_CATALOG.exists():
                entries += json.loads(
                    PRODUCT_CATALOG.read_text(encoding="utf-8")
                )["products"]
            # The price book carries a chapter key rather than a path, and its
            # products are the ones on the quotations -- they have to follow
            # the same sub-categories.
            if PRICE_BOOK.exists():
                for entry in json.loads(
                    PRICE_BOOK.read_text(encoding="utf-8")
                )["products"]:
                    key = catalog_rules.refine(entry["category"], entry["name"])
                    path = catalog_rules.CATEGORY_PATHS.get(key)
                    if path and entry.get("code"):
                        wanted[entry["code"]] = path
        for entry in entries:
            code = (entry.get("code") or "").strip()
            path = entry.get("category_path")
            if code and path:
                wanted[code] = path
        if not wanted:
            return 0
        Product = self.env["product.template"].with_context(active_test=False)
        products = Product.search([("default_code", "in", list(wanted))])
        cache = {}
        moved = 0
        for product in products:
            path = wanted.get(product.default_code)
            if not path:
                continue
            if path not in cache:
                cache[path] = self._tectora_resolve_category(path, root_name)
            category = cache[path]
            if product.categ_id == category:
                continue
            # Only move within the works tree; a category somebody chose
            # outside it is a deliberate exception.
            if not product.categ_id or self._tectora_in_tree(
                product.categ_id, root_name
            ):
                product.categ_id = category
                moved += 1
        _logger.info("tectora_products: %s products re-categorised", moved)
        return moved

    def _tectora_in_tree(self, category, root_name):
        node = category
        while node:
            if not node.parent_id and node.name == root_name:
                return True
            node = node.parent_id
        return False

    def _tectora_resolve_category(self, path, root_name):
        """Resolve (and create where missing) an 'A/B' category path under the
        root, reusing every category that already exists."""
        Category = self.env["product.category"]
        root = Category.search(
            [("name", "=", root_name), ("parent_id", "=", False)], limit=1
        )
        if not root:
            root = Category.create({"name": root_name})
        parent = root
        parts = [part.strip() for part in str(path).split("/") if part.strip()]
        # A path that already starts with the root ("Dakwerken/Afdichting")
        # must not nest the root twice.
        if parts and parts[0].lower() == root_name.lower():
            parts = parts[1:]
        for part in parts:
            if not part:
                continue
            category = Category.search(
                [("name", "=", part), ("parent_id", "=", parent.id)], limit=1
            )
            if not category:
                category = Category.create({"name": part, "parent_id": parent.id})
            parent = category
        return parent

    @api.model
    def _tectora_import_product_catalog(self, archive_price_book=True):
        """Load the shipped catalogue (data/product_catalog.json) through the
        shared applier. Idempotent; archives the old price-book products."""
        if not PRODUCT_CATALOG.exists():
            _logger.warning(
                "tectora_products: %s missing, nothing imported", PRODUCT_CATALOG
            )
            return
        data = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))
        # Current files carry category_path per product; older ones a key plus
        # a categories table.
        paths = {
            entry["key"]: entry["path"] for entry in data.get("categories", [])
        }
        entries = []
        for entry in data["products"]:
            entry = dict(entry)
            if not entry.get("category_path"):
                entry["category_path"] = paths.get(
                    entry.get("category"), catalog_rules.CATEGORY_PATHS["andere"]
                )
            entries.append(entry)
        root_name = data.get("root_category") or DEFAULT_ROOT_CATEGORY
        # The chapters nobody sells from yet exist too, so they can be filed
        # into by hand.
        counters = {"categories": self._tectora_ensure_category_tree(root_name)}
        counters.update(
            self._tectora_apply_catalog(entries, {"root_category": root_name})
        )
        counters["archived"] = self._tectora_archive_price_book(archive_price_book)
        _logger.info("tectora_products: catalogue imported (%s)", counters)
        return counters

    def _tectora_archive_price_book(self, enabled=True):
        if not enabled:
            return 0
        old = self.env["product.template"].search(
            [("default_code", "=like", "DAK-%"), ("active", "=", True)]
        )
        count = len(old)
        if old:
            old.write({"active": False})
        return count

    def _tectora_load_vendors(self, names):
        Partner = self.env["res.partner"]
        result = {}
        for name in names:
            partner = Partner.search(
                [("name", "=ilike", name), ("supplier_rank", ">", 0)], limit=1
            ) or Partner.search([("name", "=ilike", name)], limit=1)
            if not partner:
                partner = Partner.create(
                    {"name": name, "company_type": "company", "supplier_rank": 1}
                )
            elif not partner.supplier_rank:
                partner.supplier_rank = 1
            result[name] = partner
        return result

    def _tectora_refined_category(self, key, name, chapters):
        """The chapter's sub-category for this product, or the chapter itself.

        ``chapters`` is the key -> category mapping the price book brings; the
        sub-categories are not in it, so those are resolved by path.
        """
        refined = catalog_rules.refine(key, name)
        if refined == key:
            return chapters[key]
        path = catalog_rules.CATEGORY_PATHS.get(refined)
        if not path:
            return chapters[key]
        return self._tectora_resolve_category(path, DEFAULT_ROOT_CATEGORY)

    def _tectora_load_categories(self, entries):
        Category = self.env["product.category"]
        root = Category.search(
            [("name", "=", DEFAULT_ROOT_CATEGORY), ("parent_id", "=", False)],
            limit=1,
        )
        if not root:
            root = Category.create({"name": DEFAULT_ROOT_CATEGORY})
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
