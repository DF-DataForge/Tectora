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


# What a new sub-category takes over from its parent, when the field exists.
INHERITED_CATEGORY_FIELDS = (
    "tectora_usage_ids",
    "property_cost_method",
    "property_valuation",
    "property_account_income_categ_id",
    "property_account_expense_categ_id",
    "property_stock_valuation_account_id",
    "property_stock_account_input_categ_id",
    "property_stock_account_output_categ_id",
    "property_stock_journal",
    "route_ids",
    "removal_strategy_id",
)


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

        ``options["mode"] == "complete"`` only adds: missing products are
        created, an existing product (also one with the same name and no
        reference) only gets its empty reference and sales description, and
        is brought back if it was archived (a works item also becomes
        sellable again).
        """
        options = options or {}
        root_name = options.get("root_category") or DEFAULT_ROOT_CATEGORY
        # A raw material is bought, not sold; only the works items are
        # quoted. The wizard can override this per import.
        sale_ok_goods = options.get("sale_ok_goods", False)
        # "complete": create what is missing and fill an empty reference or
        # sales description, never overwrite what the database already has
        # (name, price, category, unit, vendor lines).
        complete = options.get("mode") == "complete"
        Product = self.env["product.template"]
        SupplierInfo = self.env["product.supplierinfo"]

        uoms = {}
        categories = {}
        vendors = {}
        tags = self._tectora_load_tags(entries)
        counters = {"created": 0, "updated": 0, "vendor_lines": 0,
                    "completed": 0, "unchanged": 0, "descriptions": 0,
                    "reactivated": []}

        for entry in entries:
            path = catalog_rules.branch_path(
                entry["category_path"], entry["is_service"], entry["name"]
            )
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
            if not product and complete:
                # A product made by hand without a reference, under another
                # category: the same name gets the reference instead of a twin.
                product = Product.with_context(active_test=False).search(
                    [("name", "=", entry["name"]), ("default_code", "=", False)],
                    limit=1,
                )
            if product and complete:
                fill = {}
                # In the file, so it belongs in the catalogue: an archived
                # product comes back, a works item can be sold again.
                if not product.active:
                    fill["active"] = True
                    counters["reactivated"].append(entry.get("code") or entry["name"])
                if entry["is_service"] and not product.sale_ok:
                    fill["sale_ok"] = True
                if entry.get("code") and not product.default_code:
                    fill["default_code"] = entry["code"]
                if values["description_sale"] and not (product.description_sale or "").strip():
                    fill["description_sale"] = values["description_sale"]
                    counters["descriptions"] += 1
                if fill:
                    product.write(fill)
                    counters["completed"] += 1
                else:
                    counters["unchanged"] += 1
                continue
            if product:
                product.write(values)
                counters["updated"] += 1
            else:
                product = Product.create(values)
                counters["created"] += 1
                if values["description_sale"]:
                    counters["descriptions"] += 1
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
        before = self.env["product.category"].search_count([])
        # The chapters of the roof planner hold the works items that can be
        # sold; Grondstoffen holds the raw materials, by material type.
        for path in catalog_rules.CATEGORY_PATHS.values():
            self._tectora_resolve_category(path, root_name)
        for path in catalog_rules.GOODS_TYPE_PATHS.values():
            self._tectora_resolve_category(
                "%s/%s" % (catalog_rules.GOODS_BRANCH, path), root_name
            )
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
                        # Price-book items are the works items: always sold.
                        wanted[entry["code"]] = path
        for entry in entries:
            code = (entry.get("code") or "").strip()
            path = entry.get("category_path")
            if code and path:
                # The file was generated before some sub-categories existed:
                # refine on the name, as an import does.
                path = catalog_rules.refine_path(path, entry.get("name") or "")
                wanted[code] = catalog_rules.branch_path(
                    path, entry.get("is_service", True), entry.get("name") or ""
                )
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
                moved += self._tectora_move_product(product, category)
        _logger.info("tectora_products: %s products re-categorised", moved)
        return moved

    @api.model
    def _tectora_enforce_goods_not_sellable(self):
        """Take the raw materials out of the sales catalogue.

        Only the works items are quoted; a raw material is bought. Which is
        which comes from the shipped catalogue, so a product somebody made
        sellable that the catalogue does not know about is left alone.
        """
        if not PRODUCT_CATALOG.exists():
            return 0
        entries = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))[
            "products"
        ]
        codes = [
            entry["code"]
            for entry in entries
            if entry.get("code") and not entry.get("is_service")
        ]
        if not codes:
            return 0
        goods = self.env["product.template"].with_context(active_test=False).search(
            [("default_code", "in", codes), ("sale_ok", "=", True)]
        )
        if goods:
            goods.write({"sale_ok": False})
        _logger.info("tectora_products: %s raw materials set to not sellable", len(goods))
        return len(goods)

    def _tectora_enforce_works_sellable(self):
        """Put the works items back in the sales catalogue.

        The counterpart of ``_tectora_enforce_goods_not_sellable``: the export
        names the vendor a works item's material comes from ("Leveren en
        plaatsen van de koepelschaal type: Skylux", vendor Cintralux), which
        used to file the item itself as stock -- and a raw material is not
        sellable, so a dome could not be quoted at all. Which is which comes
        from the shipped catalogue.
        """
        if not PRODUCT_CATALOG.exists():
            return 0
        entries = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))[
            "products"
        ]
        codes = [
            entry["code"]
            for entry in entries
            if entry.get("code") and entry.get("is_service")
        ]
        if not codes:
            return 0
        works = self.env["product.template"].with_context(active_test=False).search(
            ["&", ("default_code", "in", codes),
             "|", ("type", "!=", "service"), ("sale_ok", "=", False)]
        )
        if works:
            values = {"type": "service", "sale_ok": True, "purchase_ok": False}
            if "is_storable" in self.env["product.template"]._fields:
                values["is_storable"] = False
            works.write(values)
        _logger.info("tectora_products: %s works items back on sale", len(works))
        return len(works)

    @api.model
    def _tectora_refile_subcategories(self, root_name=None):
        """Move the products that sit in a chapter with sub-categories (e.g.
        04. Opbouwwerken plat dak/Afdichting) into the sub-category their name
        belongs to (Dampscherm, Dakbedekking/EPDM, ...): the works items; the raw
        materials are filed by material type instead (_tectora_refile_goods).

        Covers every product in the database, also those not in the shipped
        catalogue (added by hand or by a later import). A product in a
        sub-category already, or outside the works tree, is left alone.
        """
        root_name = root_name or DEFAULT_ROOT_CATEGORY
        Product = self.with_context(active_test=False)
        cache = {}
        moved = 0
        for key in catalog_rules.SUBCATEGORY_RULES:
            chapter = catalog_rules.CATEGORY_PATHS.get(key)
            if not chapter:
                continue
            # The works items only: the raw materials go by material type
            # (_tectora_refile_goods).
            category = self._tectora_find_category(chapter, root_name)
            if not category:
                continue
            for product in Product.search([("categ_id", "=", category.id)]):
                refined = catalog_rules.refine_path(chapter, product.name)
                if refined == chapter:
                    continue
                if refined not in cache:
                    cache[refined] = self._tectora_resolve_category(refined, root_name)
                    # Offered in the drawing where its products were.
                    target = cache[refined]
                    if "tectora_usage_ids" in target._fields and category.tectora_usage_ids:
                        target.tectora_usage_ids = target.tectora_usage_ids | category.tectora_usage_ids
                moved += self._tectora_move_product(product, cache[refined])
        _logger.info("tectora_products: %s products moved to a sub-category", moved)
        return moved

    @api.model
    def _tectora_refile_goods(self, root_name=None):
        """File every raw material (the Grondstoffen branch) by its material
        type -- Dakbanen, Isolatie, Zinkwerk, Bevestigingsmaterialen, ... --
        instead of by the quotation chapter it used to mirror, then remove the
        old chapter categories of the branch that are left empty."""
        root_name = root_name or DEFAULT_ROOT_CATEGORY
        branch = self._tectora_find_category(catalog_rules.GOODS_BRANCH, root_name)
        if not branch:
            return 0
        Category = self.env["product.category"]
        Product = self.with_context(active_test=False)
        cache = {}
        moved = 0
        prefix = "%s/" % catalog_rules.GOODS_BRANCH
        for product in Product.search([("categ_id", "child_of", branch.id)]):
            current = self._tectora_category_path(product.categ_id, root_name)
            wanted = catalog_rules.goods_path(product.name, current)
            if wanted == current:
                continue
            if wanted not in cache:
                cache[wanted] = self._tectora_resolve_category(wanted, root_name)
            moved += self._tectora_move_product(product, cache[wanted])
        # The mirrored chapters (Grondstoffen/02. Dakranden, ...) that no
        # product uses any more.
        keep = {prefix + path for path in catalog_rules.GOODS_TYPE_PATHS.values()}
        keep |= {prefix + path.split("/")[0] for path in catalog_rules.GOODS_TYPE_PATHS.values()}
        removed = 0
        candidates = Category.search([("id", "child_of", branch.id), ("id", "!=", branch.id)])
        for category in candidates.sorted(lambda c: -len(c.parent_path or "")):
            if not category.exists():
                continue
            path = self._tectora_category_path(category, root_name)
            if path in keep or Category.search_count([("id", "child_of", category.id), ("id", "!=", category.id)]):
                continue
            if Product.search_count([("categ_id", "=", category.id)]):
                continue
            try:
                with self.env.cr.savepoint():
                    category.unlink()
                removed += 1
            except Exception:  # still referenced elsewhere: leave it
                _logger.info("tectora_products: category %s kept", category.complete_name)
        _logger.info(
            "tectora_products: %s raw materials filed by type, %s empty categories removed",
            moved, removed,
        )
        return moved

    def _tectora_move_product(self, product, category):
        """Put ``product`` in ``category``; 1 when it moved. A product that
        cannot move (stock valuation, a constraint) stays where it is and is
        logged: re-filing never makes an upgrade fail."""
        try:
            with self.env.cr.savepoint():
                product.categ_id = category
                product.flush_recordset(["categ_id"])
            return 1
        except Exception as error:  # noqa: BLE001
            _logger.warning(
                "tectora_products: %s not moved to %s: %s",
                product.display_name, category.complete_name, error,
            )
            return 0

    def _tectora_category_path(self, category, root_name):
        """The 'A/B' path of ``category`` under the root."""
        names = []
        node = category
        while node and not (not node.parent_id and node.name == root_name):
            names.append(node.name)
            node = node.parent_id
        return "/".join(reversed(names))

    def _tectora_find_category(self, path, root_name):
        """The category at ``path`` under the root, without creating it."""
        Category = self.env["product.category"]
        node = Category.search([("name", "=", root_name), ("parent_id", "=", False)], limit=1)
        for part in [p.strip() for p in str(path).split("/") if p.strip()]:
            if not node:
                break
            node = Category.search([("name", "=", part), ("parent_id", "=", node.id)], limit=1)
        return node

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
                values = {"name": part, "parent_id": parent.id}
                # A new sub-category is offered where its parent is (the
                # drawing's usages, when Dakmeting is installed) and keeps its
                # parent's costing, valuation, accounts and routes: moving a
                # product with stock into it changes nothing in accounting.
                for field_name in INHERITED_CATEGORY_FIELDS:
                    field = Category._fields.get(field_name)
                    if not field or not parent[field_name]:
                        continue
                    value = parent[field_name]
                    if field.type == "many2many":
                        values[field_name] = [(6, 0, value.ids)]
                    elif field.type == "many2one":
                        values[field_name] = value.id
                    else:
                        values[field_name] = value
                category = Category.create(values)
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
                # Odoo 20 derives "is a company" from the VAT number; the
                # price book carries none, so the vendor is a plain contact.
                partner = Partner.create({"name": name, "supplier_rank": 1})
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
