# -*- coding: utf-8 -*-
import json
import logging
import re
from pathlib import Path

from odoo import api, fields, models

from . import bom_rules

_logger = logging.getLogger(__name__)

BOM_CATALOG = Path(__file__).parent.parent / "data" / "bom_catalog.json"

# More bills of materials than this on one product is reported: a variant range
# can legitimately be long, but it is also what a run of false product matches
# looks like.
CROWDED = 12


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    # Odoo offers only goods here ("[('type', '=', 'consu')]"), but the works
    # items Tectora sells are services -- that is what a quotation line is --
    # and those are exactly the products whose bill of materials tells the crew
    # what to load. Nothing in mrp enforces the type beyond this domain:
    # explode() never looks at the parent's type. (_bom_find does drop
    # services, which is why sale.order looks its BoM up itself.)
    product_tmpl_id = fields.Many2one(
        domain="[('type', 'in', ['consu', 'service'])]"
    )
    product_id = fields.Many2one(
        domain="['&', ('product_tmpl_id', '=', product_tmpl_id), "
        "('type', 'in', ['consu', 'service'])]"
    )

    tectora_bom_key = fields.Char(
        string="Stuklijstsleutel (import)",
        index=True,
        copy=False,
        help="Sleutel uit de geïmporteerde stuklijstexport: zelfde product en "
        "zelfde regels geeft dezelfde sleutel. Zo werkt een tweede import "
        "bij in plaats van te verdubbelen.",
    )

    # ------------------------------------------------------------------ import
    @api.model
    def _tectora_product_index(self):
        """Everything the matcher needs about the catalogue, in one query."""
        products = self.env["product.product"].search_read(
            [("active", "=", True)],
            ["default_code", "name", "uom_id", "product_tmpl_id", "type"],
        )
        rows = [
            {
                "id": row["id"],
                "code": row["default_code"] or "",
                "name": row["name"] or "",
                "uom_id": row["uom_id"] and row["uom_id"][0],
                "tmpl_id": row["product_tmpl_id"] and row["product_tmpl_id"][0],
                "type": row["type"],
            }
            for row in products
        ]
        by_name = {}
        by_supplier = {}
        by_namecode = {}
        for row in rows:
            by_name.setdefault(bom_rules.norm(row["name"]), row)
            if row["code"]:
                by_supplier.setdefault(bom_rules.canon(row["code"]), row)
        # A supplier's article code is often only in the vendor pricelist.
        by_tmpl = {}
        for row in rows:
            by_tmpl.setdefault(row["tmpl_id"], row)
        for line in self.env["product.supplierinfo"].search_read(
            [("product_code", "!=", False)], ["product_code", "product_tmpl_id"]
        ):
            key = bom_rules.canon(line["product_code"])
            if key in by_supplier or not line["product_tmpl_id"]:
                continue
            match = by_tmpl.get(line["product_tmpl_id"][0])
            if match:
                by_supplier[key] = match
        for row in rows:
            for code in re.findall(r"\b\d{6,}\b", row["name"]):
                by_namecode.setdefault(bom_rules.canon(code), row)
        return rows, by_name, by_supplier, by_namecode

    @api.model
    def _tectora_match_export(self, boms, options=None):
        """Resolve every BoM and every component against the catalogue.

        Returns (plan, report). The plan is what ``_tectora_apply_plan`` writes;
        the report is what the wizard shows, and it is complete whether or not
        anything gets written -- so a dry run and a real import say the same
        thing about the file.
        """
        options = options or {}
        product_min = options.get("product_min", bom_rules.AUTO)
        component_min = options.get("component_min", bom_rules.AUTO)
        uom_policy = options.get("uom_policy", "base_only")

        rows, by_name, by_supplier, by_namecode = self._tectora_product_index()
        # Components can be anything in the catalogue; parents are only what
        # Tectora sells -- the works items, which both the price book and the
        # catalogue carry as services.
        index = bom_rules.build_index(rows)
        sellable_rows = [
            r for r in rows
            if r["type"] == "service" or r["code"].upper().startswith("DAK")
        ]
        sellable = bom_rules.build_index(sellable_rows) if sellable_rows else index

        product_cache = {}
        component_cache = {}
        report = {
            "boms": len(boms),
            "lines": sum(len(b["lines"]) for b in boms),
            "planned": 0,
            "planned_lines": 0,
            "duplicates": 0,
            "no_product": [],
            "no_component": [],
            "uom_skipped": [],
            "uom_converted": [],
            "products": {"auto": 0, "review": 0, "manual": 0},
            "components": {"auto": 0, "review": 0, "manual": 0},
        }
        plan = []
        seen = set()
        counters = {}
        labels = {}

        for bom in boms:
            name = bom["product"]
            if name not in product_cache:
                score, product = bom_rules.match_product(name, sellable)
                product_cache[name] = (score, product)
                report["products"][bom_rules.confidence(score)] += 1
            score, product = product_cache[name]
            if not product or score < product_min:
                report["no_product"].append((name, round(score, 2)))
                continue

            key = bom_rules.signature(bom)
            if key in seen:
                report["duplicates"] += 1
                continue
            seen.add(key)

            lines = []
            for line in bom["lines"]:
                component = line["component"]
                if component not in component_cache:
                    result = bom_rules.match_component(
                        component, index, by_supplier, by_namecode, by_name
                    )
                    component_cache[component] = result
                    report["components"][bom_rules.confidence(result[0])] += 1
                c_score, c_product, method, why = component_cache[component]
                if not c_product or c_score < component_min:
                    report["no_component"].append(
                        (component, round(c_score, 2), name)
                    )
                    continue
                qty = line["qty"]
                factor = bom_rules.packaging_factor(line["uom"])
                if factor:
                    if uom_policy == "base_only":
                        report["uom_skipped"].append(
                            (component, line["uom"], qty, name)
                        )
                        continue
                    if uom_policy == "convert":
                        qty = round(qty * factor, 6)
                        report["uom_converted"].append(
                            (component, line["uom"], line["qty"], qty)
                        )
                if qty <= 0:
                    continue
                lines.append({
                    "product_id": c_product["id"],
                    "product_qty": qty,
                    "product_uom_id": c_product["uom_id"],
                    "sequence": len(lines) + 1,
                    "_component": component,
                    "_method": method,
                    "_why": why,
                })
            if not lines:
                continue

            counters[product["id"]] = counters.get(product["id"], 0) + 1
            # Several BoMs on one product must stay tellable apart in the UI:
            # the variant label is the natural reference, numbered when the
            # export gives two BoMs the same one.
            label = bom_rules.variant_label(bom) or bom["reference"] or name[:60]
            used = labels.setdefault(product["id"], {})
            used[label] = used.get(label, 0) + 1
            if used[label] > 1:
                label = "%s (%s)" % (label, used[label])
            plan.append({
                "key": key,
                "product": product,
                "source_product": name,
                "code": label,
                "type": bom["type"],
                "sequence": counters[product["id"]],
                "lines": lines,
            })
            report["planned"] += 1
            report["planned_lines"] += len(lines)
        # Many BoMs on one product is normal for a variant range, but a lot of
        # them usually means several source products matched the same one -- so
        # it is worth naming rather than leaving to be discovered later.
        names = {
            entry["product"]["id"]: entry["product"]["code"]
            or entry["product"]["name"]
            for entry in plan
        }
        report["crowded"] = sorted(
            (
                (names[product_id], count)
                for product_id, count in counters.items()
                if count > CROWDED and product_id in names
            ),
            key=lambda item: -item[1],
        )
        return plan, report

    @api.model
    def _tectora_apply_plan(self, plan):
        """Create or update the planned BoMs. Idempotent on tectora_bom_key."""
        Uom = self.env["uom.uom"]
        default_uom = Uom.search([], limit=1, order="id")
        created = updated = 0
        existing = {
            bom.tectora_bom_key: bom
            for bom in self.with_context(active_test=False).search(
                [("tectora_bom_key", "in", [entry["key"] for entry in plan])]
            )
        }
        for entry in plan:
            product = entry["product"]
            values = {
                "product_tmpl_id": product["tmpl_id"],
                "product_qty": 1.0,
                "product_uom_id": product["uom_id"] or default_uom.id,
                "type": entry["type"],
                "code": entry["code"],
                "sequence": entry["sequence"],
                "tectora_bom_key": entry["key"],
                "bom_line_ids": [
                    (0, 0, {k: v for k, v in line.items() if not k.startswith("_")})
                    for line in entry["lines"]
                ],
            }
            bom = existing.get(entry["key"])
            if bom:
                # Replace the lines rather than merge: the export is the source
                # of truth for what a stuklijst contains.
                bom.bom_line_ids.unlink()
                bom.write(values)
                updated += 1
            else:
                self.create(values)
                created += 1
        return {"created": created, "updated": updated}

    @api.model
    def _tectora_import_shipped_boms(self, options=None):
        """Load data/bom_catalog.json -- what install and upgrade run.

        Only the confident matches are created: the products and components
        are matched on their names, so a lower threshold would attach material
        to the wrong works item. The rest is for the wizard, once the mapping
        in docs/stuklijst_koppeling.md has been confirmed.
        """
        if not BOM_CATALOG.exists():
            _logger.warning(
                "tectora_boms: %s missing, no bills of materials loaded",
                BOM_CATALOG,
            )
            return {}
        data = json.loads(BOM_CATALOG.read_text(encoding="utf-8"))
        boms = data.get("boms") or []
        if not boms:
            _logger.warning("tectora_boms: %s holds no bills of materials", BOM_CATALOG)
            return {}
        settings = {
            "product_min": bom_rules.AUTO,
            "component_min": bom_rules.AUTO,
            "uom_policy": "base_only",
            "dry_run": False,
        }
        settings.update(options or {})
        report = self._tectora_import_boms(boms, settings)
        _logger.info(
            "tectora_boms: %s of %s bills of materials loaded from %s "
            "(%s created, %s updated, %s lines); %s skipped for want of a "
            "product, %s lines for want of a component, %s lines because the "
            "quantity is in a packaging unit",
            report.get("planned"), report.get("boms"), data.get("source"),
            report.get("created"), report.get("updated"),
            report.get("planned_lines"), len(report.get("no_product") or []),
            len(report.get("no_component") or []),
            len(report.get("uom_skipped") or []),
        )
        return report

    @api.model
    def _tectora_import_boms(self, boms, options=None):
        options = options or {}
        plan, report = self._tectora_match_export(boms, options)
        if options.get("dry_run"):
            report.update({"created": 0, "updated": 0, "dry_run": True})
            return report
        report.update(self._tectora_apply_plan(plan))
        report["dry_run"] = False
        _logger.info(
            "tectora_boms: %(created)s stuklijsten aangemaakt, %(updated)s "
            "bijgewerkt, %(planned_lines)s regels", report
        )
        return report
