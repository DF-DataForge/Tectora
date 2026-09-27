# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

from odoo import api, models

_logger = logging.getLogger(__name__)

QUOTATION_TEMPLATES = (
    Path(__file__).parent.parent / "data" / "quotation_templates.json"
)
# Templates are addressed by external id so a renamed template is still
# recognised on the next import instead of being created a second time.
XMLID_MODULE = "tectora_products"
XMLID_PREFIX = "quotation_template_"


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    @api.model
    def _tectora_import_quotation_templates(self, refresh=False):
        """Load the twenty starting points from data/quotation_templates.json.

        Every template opens with the general works and the mandatory safety
        measures, then the demolition (renovation only), the roof build-up
        (vapour barrier, one insulation, one membrane), the roof edge with the
        corners that belong to it, and the rainwater drainage. What sales
        rarely needs is offered as optional lines.

        Idempotent. An existing template keeps its lines -- they are what the
        office tuned -- unless it has none or ``refresh`` is set; its name,
        validity and terms always follow the file.
        """
        if not QUOTATION_TEMPLATES.exists():
            _logger.warning(
                "tectora_products: %s missing, no quotation templates imported",
                QUOTATION_TEMPLATES,
            )
            return {}
        data = json.loads(QUOTATION_TEMPLATES.read_text(encoding="utf-8"))
        templates = data.get("templates") or []
        products = self._tectora_template_products(templates)

        counters = {"created": 0, "updated": 0, "relined": 0, "missing": 0}
        missing = set()
        for position, entry in enumerate(templates):
            xml_id = "%s.%s%s" % (XMLID_MODULE, XMLID_PREFIX, entry["key"])
            template = self.env.ref(xml_id, raise_if_not_found=False)
            values = {
                "name": entry["name"],
                "note": entry.get("note") or False,
                "number_of_days": entry.get("number_of_days") or 0,
            }
            lines, unknown = self._tectora_template_lines(entry, products)
            missing |= unknown
            if template:
                template.write(values)
                counters["updated"] += 1
                if refresh or not template.sale_order_template_line_ids:
                    template.sale_order_template_line_ids.unlink()
                    template.write({"sale_order_template_line_ids": lines})
                    counters["relined"] += 1
                continue
            values["sale_order_template_line_ids"] = lines
            # The renovations first, then the new builds, in the order of the
            # file rather than alphabetically.
            values["sequence"] = 10 + position
            template = self.create(values)
            self.env["ir.model.data"]._update_xmlids(
                [{
                    "xml_id": xml_id,
                    "record": template,
                    # The office owns its templates once they exist; an
                    # upgrade must not overwrite what it changed.
                    "noupdate": True,
                }]
            )
            counters["created"] += 1
        counters["missing"] = len(missing)
        if missing:
            _logger.warning(
                "tectora_products: %s products of the quotation templates are "
                "not in the database (%s)",
                len(missing), ", ".join(sorted(missing)),
            )
        _logger.info("tectora_products: quotation templates imported (%s)", counters)
        return counters

    def _tectora_template_products(self, templates):
        """default_code -> product.product for every code the file uses."""
        codes = {
            item["code"]
            for entry in templates
            for item in entry["lines"]
            if item.get("code")
        }
        if not codes:
            return {}
        products = self.env["product.product"].search(
            [("default_code", "in", list(codes))]
        )
        return {product.default_code: product for product in products}

    def _tectora_template_lines(self, entry, products):
        """(create commands, codes not found). A line whose product is missing
        is skipped rather than silently quoted as something else."""
        commands = []
        unknown = set()
        sequence = 0
        for item in entry["lines"]:
            sequence += 10
            if item.get("section"):
                commands.append((0, 0, {
                    "sequence": sequence,
                    "display_type": "line_section",
                    "name": item["section"],
                    "is_optional": bool(item.get("optional")),
                }))
                continue
            product = products.get(item["code"])
            if not product:
                unknown.add(item["code"])
                sequence -= 10
                continue
            commands.append((0, 0, {
                "sequence": sequence,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "product_uom_qty": item["quantity"],
                "is_optional": bool(item.get("optional")),
            }))
        return commands, unknown
